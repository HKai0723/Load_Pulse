"""將 1,603 份澳洲 AEMO 原始月 CSV 無損打包為單一 Parquet，並產出完整指紋總清單。

輸入（完全唯讀，絕不修改）：
- data/raw/Australia_AEMO/raw_manifest.json
- data/raw/Australia_AEMO/{REGION}/AU_AEMO_{REGION}_RAW_{YYYYMM}.csv (1,603 檔)
- data/external/au_public_holidays.csv
- data/external/au_emergency_closures.csv

輸出：
- data/processed/AU_AEMO_NEM_raw_1998_2026.parquet (pyarrow + zstd)
- data/processed/raw_bundle_manifest.json (頂層快篩總指紋 + 1,605 檔獨立 SHA-256 明細)
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_AEMO_DIR = PROJECT_ROOT / "data" / "raw" / "Australia_AEMO"
RAW_MANIFEST_PATH = RAW_AEMO_DIR / "raw_manifest.json"
EXTERNAL_FILES = [
    PROJECT_ROOT / "data" / "external" / "au_public_holidays.csv",
    PROJECT_ROOT / "data" / "external" / "au_emergency_closures.csv",
]

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_PARQUET_PATH = PROCESSED_DIR / "AU_AEMO_NEM_raw_1998_2026.parquet"
OUTPUT_MANIFEST_PATH = PROCESSED_DIR / "raw_bundle_manifest.json"

EXPECTED_RAW_COLUMNS = ["REGION", "SETTLEMENTDATE", "TOTALDEMAND", "RRP", "PERIODTYPE"]
OUTPUT_COLUMNS = [*EXPECTED_RAW_COLUMNS, "source_file"]
PARQUET_COMPRESSION = "zstd"
HASH_SPEC = (
    "SHA-256 of UTF-8 encoded lines formatted as '{relative_path}:{sha256}\\n', "
    "with all source files normalized to POSIX relative paths from project root "
    "and sorted in ascending lexicographical order by relative_path."
)


def compute_sha256(file_path: Path) -> str:
    """以串流方式計算本地檔案之 SHA-256 十六進位雜湊值。"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def to_posix_relpath(file_path: Path) -> str:
    """將專案內檔案路徑轉為相對於專案根目錄的 POSIX 路徑（`/` 分隔）。"""
    return file_path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()


def load_and_verify_raw_manifest() -> tuple[list[dict], str]:
    """唯讀載入 raw_manifest.json 並逐一驗證 1,603 份原始 CSV 存在性與 SHA-256。"""
    if not RAW_MANIFEST_PATH.exists():
        raise FileNotFoundError(f"找不到原始清單檔：{RAW_MANIFEST_PATH}")

    raw_manifest_sha256 = compute_sha256(RAW_MANIFEST_PATH)
    manifest = json.loads(RAW_MANIFEST_PATH.read_text(encoding="utf-8"))
    files_map: dict[str, dict] = manifest.get("files", {})

    if not files_map:
        raise ValueError(f"raw_manifest.json 中沒有任何檔案紀錄：{RAW_MANIFEST_PATH}")

    # 依 (region_id, ym) 升冪排序
    ordered_entries: list[dict] = []
    for rel_key, meta in files_map.items():
        region_id = str(meta["region"])
        ym = str(meta["ym"])
        ordered_entries.append(
            {
                "rel_key": rel_key,
                "region_id": region_id,
                "ym": ym,
                "expected_sha256": str(meta["sha256"]).lower(),
                "manifest_rows": int(meta["rows"]),
                "manifest_bytes": int(meta["bytes"]),
                "path": RAW_AEMO_DIR / rel_key,
            }
        )
    ordered_entries.sort(key=lambda item: (item["region_id"], item["ym"]))

    mismatches: list[str] = []
    for item in ordered_entries:
        p: Path = item["path"]
        if not p.exists():
            mismatches.append(f"MISSING: {item['rel_key']}")
            continue

        actual_sha = compute_sha256(p).lower()
        if actual_sha != item["expected_sha256"]:
            mismatches.append(
                f"SHA256_MISMATCH: {item['rel_key']} "
                f"(expected={item['expected_sha256']}, actual={actual_sha})"
            )
            continue

        item["actual_sha256"] = actual_sha
        item["actual_bytes"] = p.stat().st_size

    if mismatches:
        preview = "\n".join(mismatches[:20])
        raise RuntimeError(
            f"原始 CSV SHA-256 檢核失敗，共 {len(mismatches)} 檔不符或缺失：\n{preview}"
        )

    print(
        f"[1/4] 原始檔 SHA-256 驗證通過：共 {len(ordered_entries)} 檔，0 檔不符。"
    )
    return ordered_entries, raw_manifest_sha256


def build_parquet_from_raw(ordered_entries: list[dict]) -> tuple[list[dict], int]:
    """依 (region_id, ym) 順序無損讀取 1,603 份原始 CSV 並輸出為 ZSTD 壓縮 Parquet。"""
    chunks: list[pd.DataFrame] = []
    raw_source_records: list[dict] = []

    for item in ordered_entries:
        p: Path = item["path"]
        df = pd.read_csv(
            p,
            dtype={
                "REGION": "string",
                "SETTLEMENTDATE": "string",
                "TOTALDEMAND": "float64",
                "RRP": "float64",
                "PERIODTYPE": "string",
            },
            keep_default_na=True,
            na_values=[""],
        )

        if list(df.columns) != EXPECTED_RAW_COLUMNS:
            raise ValueError(
                f"欄位結構不符：{p.name} 實際為 {list(df.columns)}，預期為 {EXPECTED_RAW_COLUMNS}"
            )

        df["source_file"] = p.name
        chunks.append(df)

        raw_source_records.append(
            {
                "relative_path": to_posix_relpath(p),
                "file_name": p.name,
                "source_type": "raw_aemo",
                "region_id": item["region_id"],
                "rows": int(len(df)),
                "bytes": int(item["actual_bytes"]),
                "sha256": item["actual_sha256"],
            }
        )

    full_df = pd.concat(chunks, ignore_index=True)

    # source_file 採 dictionary/category 編碼以節省空間
    source_categories = [item["path"].name for item in ordered_entries]
    full_df["source_file"] = pd.Categorical(
        full_df["source_file"],
        categories=source_categories,
        ordered=False,
    )

    schema = pa.schema(
        [
            pa.field("REGION", pa.string()),
            pa.field("SETTLEMENTDATE", pa.string()),
            pa.field("TOTALDEMAND", pa.float64()),
            pa.field("RRP", pa.float64()),
            pa.field("PERIODTYPE", pa.string()),
            pa.field("source_file", pa.dictionary(pa.int16(), pa.string())),
        ]
    )

    table = pa.Table.from_pandas(full_df[OUTPUT_COLUMNS], schema=schema, preserve_index=False)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, OUTPUT_PARQUET_PATH, compression=PARQUET_COMPRESSION)

    total_rows = int(table.num_rows)
    print(
        f"[2/4] 無損整合 Parquet 寫入完成：{OUTPUT_PARQUET_PATH.name} "
        f"({total_rows:,} 筆, {OUTPUT_PARQUET_PATH.stat().st_size / (1024 * 1024):.2f} MB)"
    )
    return raw_source_records, total_rows


def inspect_external_sources() -> list[dict]:
    """唯讀計算外部靜態 CSV（國定假日、緊急停班）之列數、大小與 SHA-256。"""
    records: list[dict] = []
    for ext_path in EXTERNAL_FILES:
        if not ext_path.exists():
            raise FileNotFoundError(f"找不到外部資料檔：{ext_path}")

        df_ext = pd.read_csv(ext_path, dtype=str)
        records.append(
            {
                "relative_path": to_posix_relpath(ext_path),
                "file_name": ext_path.name,
                "source_type": "external",
                "region_id": "ALL",
                "rows": int(len(df_ext)),
                "bytes": int(ext_path.stat().st_size),
                "sha256": compute_sha256(ext_path).lower(),
            }
        )
    print(f"[3/4] 外部靜態 CSV 檢核完成：共 {len(records)} 檔。")
    return records


def compute_master_sources_sha256(sorted_sources: list[dict]) -> str:
    """依相對路徑升冪排序之全部來源檔計算頂層快篩總指紋。"""
    h = hashlib.sha256()
    for rec in sorted_sources:
        line = f"{rec['relative_path']}:{rec['sha256']}\n"
        h.update(line.encode("utf-8"))
    return h.hexdigest()


def write_bundle_manifest(
    raw_records: list[dict],
    ext_records: list[dict],
    total_parquet_rows: int,
    raw_manifest_sha256: str,
) -> dict:
    """彙整 1,605 個來源檔並寫出 raw_bundle_manifest.json。"""
    all_sources = sorted(
        [*raw_records, *ext_records],
        key=lambda rec: rec["relative_path"],
    )
    master_sha256 = compute_master_sources_sha256(all_sources)

    parquet_bytes = int(OUTPUT_PARQUET_PATH.stat().st_size)
    parquet_sha256 = compute_sha256(OUTPUT_PARQUET_PATH).lower()

    bundle_manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "master_sources_sha256": master_sha256,
        "hash_spec": HASH_SPEC,
        "source_counts": {
            "raw_aemo": len(raw_records),
            "external": len(ext_records),
            "total": len(all_sources),
        },
        "output_parquet": {
            "path": to_posix_relpath(OUTPUT_PARQUET_PATH),
            "rows": total_parquet_rows,
            "bytes": parquet_bytes,
            "size_mb": round(parquet_bytes / (1024 * 1024), 4),
            "compression": PARQUET_COMPRESSION,
            "columns": OUTPUT_COLUMNS,
            "sha256": parquet_sha256,
        },
        "raw_manifest_ref": {
            "path": to_posix_relpath(RAW_MANIFEST_PATH),
            "sha256": raw_manifest_sha256.lower(),
        },
        "sources": all_sources,
    }

    OUTPUT_MANIFEST_PATH.write_text(
        json.dumps(bundle_manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        f"[4/4] 總指紋清單已輸出：{OUTPUT_MANIFEST_PATH.name} "
        f"(sources={len(all_sources)}, master_sha256={master_sha256[:16]}...)"
    )
    return bundle_manifest


def main() -> None:
    ordered_entries, raw_manifest_sha256 = load_and_verify_raw_manifest()
    raw_records, total_rows = build_parquet_from_raw(ordered_entries)
    ext_records = inspect_external_sources()
    write_bundle_manifest(
        raw_records=raw_records,
        ext_records=ext_records,
        total_parquet_rows=total_rows,
        raw_manifest_sha256=raw_manifest_sha256,
    )


if __name__ == "__main__":
    main()
