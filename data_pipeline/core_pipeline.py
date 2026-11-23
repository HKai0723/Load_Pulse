"""LoadPulse 澳洲全歷史電力負載標準化清洗核心模組 (v2.0.0)。

設計原則：
- 全面向量化（零列級 Python `.apply()`），完全相容 `pandas 3.0.2` Copy-on-Write 與 `pyarrow`。
- 啟動前強制以 `raw_bundle_manifest.json` 驗證輸入 Parquet 與外部靜態 CSV 之 SHA-256 完整性。
- 忠實保留所有物理觀測值（停用硬性 MW 上下限與 `1.5×IQR` 極端值過濾），僅標記結構性缺值與樣本數完整性。
- 以 `(region_id, timestamp_utc)` 為唯一複合主鍵產出長表，並整合各州民用時區、DST、國定假日、緊急停班、疫情旗標與三層 SHA-256 溯源資訊。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

PIPELINE_VERSION = "2.0.0"

MARKET_TZ = "Australia/Brisbane"  # AEMO NEM 市場全年固定 AEST (UTC+10，無 DST)
FIVE_MIN_SWITCH_AEST_NAIVE = pd.Timestamp("2021-10-01 00:00:00")
FIVE_MIN_SWITCH_UTC = pd.Timestamp("2021-09-30 14:00:00+00:00")

COVID_START_DATE = "2020-01-30"
COVID_END_DATE = "2023-05-05"

REGION_TZ_MAP: dict[str, str] = {
    "NSW1": "Australia/Sydney",
    "QLD1": "Australia/Brisbane",
    "SA1": "Australia/Adelaide",
    "TAS1": "Australia/Hobart",
    "VIC1": "Australia/Melbourne",
}

REGION_STD_OFFSET_SEC: dict[str, int] = {
    "NSW1": 10 * 3600,
    "QLD1": 10 * 3600,
    "SA1": int(9.5 * 3600),
    "TAS1": 10 * 3600,
    "VIC1": 10 * 3600,
}

MAIN_COLUMNS: list[str] = [
    "region_id",
    "timestamp_utc",
    "local_date",
    "local_hour",
    "day_of_week",
    "is_weekend",
    "is_dst",
    "load_mw",
    "day_type",
    "is_public_holiday",
    "is_emergency_closure",
    "is_covid_period",
    "is_missing",
    "quality_flag",
]

QC_EXTRA_COLUMNS: list[str] = [
    "iana_tz",
    "timestamp_local",
    "raw_interval_min",
    "sample_count",
    "expected_samples",
    "is_partial_hour",
    "is_duplicate",
    "is_dst_transition",
    "holiday_name",
    "emergency_event_category",
    "emergency_scope",
    "source_file",
    "source_file_sha256",
    "version",
]

FULL_QC_COLUMNS: list[str] = [*MAIN_COLUMNS, *QC_EXTRA_COLUMNS]

PARQUET_COMPRESSION = "zstd"


# ==========================================
# 1. SHA-256 驗真與唯讀載入
# ==========================================
def compute_sha256(file_path: Path) -> str:
    """串流計算本地檔案之 SHA-256 十六進位指紋。"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_and_load_raw_parquet(
    project_root: Path,
    bundle_manifest_path: Path,
    raw_parquet_path: Path,
    holidays_csv_path: Path,
    emergency_csv_path: Path,
) -> tuple[pd.DataFrame, dict]:
    """依 raw_bundle_manifest.json 驗證輸入檔 SHA-256，通過後唯讀載入原始整合 Parquet。"""
    if not bundle_manifest_path.exists():
        raise FileNotFoundError(f"找不到總指紋清單：{bundle_manifest_path}")

    manifest = json.loads(bundle_manifest_path.read_text(encoding="utf-8"))
    sources = manifest.get("sources", [])
    sources_by_rel = {item["relative_path"]: item for item in sources}

    def _rel_posix(p: Path) -> str:
        return p.resolve().relative_to(project_root.resolve()).as_posix()

    # 1) 驗證 AU_AEMO_NEM_raw_1998_2026.parquet
    if not raw_parquet_path.exists():
        raise FileNotFoundError(f"找不到原始整合 Parquet：{raw_parquet_path}")
    expected_raw_pq_sha = str(manifest["output_parquet"]["sha256"]).lower()
    actual_raw_pq_sha = compute_sha256(raw_parquet_path).lower()
    if actual_raw_pq_sha != expected_raw_pq_sha:
        raise RuntimeError(
            f"SHA-256 驗證失敗 ({raw_parquet_path.name}): "
            f"expected={expected_raw_pq_sha}, actual={actual_raw_pq_sha}"
        )

    # 2) 驗證兩份外部靜態 CSV
    ext_hashes: dict[str, str] = {}
    for key_name, ext_path in [
        ("external_holidays_sha256", holidays_csv_path),
        ("external_emergency_sha256", emergency_csv_path),
    ]:
        if not ext_path.exists():
            raise FileNotFoundError(f"找不到外部事件表：{ext_path}")
        rel = _rel_posix(ext_path)
        if rel not in sources_by_rel:
            raise KeyError(f"raw_bundle_manifest.json 缺少外部檔案紀錄：{rel}")
        expected_sha = str(sources_by_rel[rel]["sha256"]).lower()
        actual_sha = compute_sha256(ext_path).lower()
        if actual_sha != expected_sha:
            raise RuntimeError(
                f"SHA-256 驗證失敗 ({ext_path.name}): "
                f"expected={expected_sha}, actual={actual_sha}"
            )
        ext_hashes[key_name] = actual_sha

    # 3) 建立 source_file -> 64 碼 SHA-256 映射表
    source_file_sha256_map = {
        str(item["file_name"]): str(item["sha256"]).lower()
        for item in sources
        if item.get("source_type") == "raw_aemo"
    }

    # 4) 僅載入必要欄位（直接捨棄 RRP 與 PERIODTYPE）
    df_raw = pd.read_parquet(
        raw_parquet_path,
        columns=["REGION", "SETTLEMENTDATE", "TOTALDEMAND", "source_file"],
        engine="pyarrow",
    )

    master_sources_sha256 = str(manifest["master_sources_sha256"]).lower()
    version_tag = (
        f"v{PIPELINE_VERSION}"
        f"+src.{master_sources_sha256[:12]}"
        f"+raw.{actual_raw_pq_sha[:12]}"
    )

    lineage = {
        "pipeline_version": PIPELINE_VERSION,
        "version_tag": version_tag,
        "master_sources_sha256": master_sources_sha256,
        "input_raw_parquet_sha256": actual_raw_pq_sha,
        "external_holidays_sha256": ext_hashes["external_holidays_sha256"],
        "external_emergency_sha256": ext_hashes["external_emergency_sha256"],
        "source_file_sha256_map": source_file_sha256_map,
        "raw_row_count": int(len(df_raw)),
    }
    print(
        f"[1/6] SHA-256 啟動驗真通過 (raw Parquet + 2 external CSVs)，"
        f"載入 {len(df_raw):,} 筆原始紀錄 | version={version_tag}"
    )
    return df_raw, lineage


# ==========================================
# 2. 時間解析與分段區間平移 (AEST -> UTC)
# ==========================================
def parse_and_shift_timestamps(df_raw: pd.DataFrame) -> pd.DataFrame:
    """解析混合格式 SETTLEMENTDATE，依 2021-10-01 切換點平移為區間起點並轉為 UTC。"""
    dt_end = pd.to_datetime(df_raw["SETTLEMENTDATE"], format="mixed")
    nat_count = int(dt_end.isna().sum())
    if nat_count > 0:
        raise ValueError(f"SETTLEMENTDATE 解析出現 {nat_count} 筆 NaT")

    raw_interval_min = np.where(dt_end <= FIVE_MIN_SWITCH_AEST_NAIVE, 30, 5).astype(np.int8)
    dt_start_aest = dt_end - pd.to_timedelta(raw_interval_min, unit="min")
    ts_utc = (
        dt_start_aest.dt.tz_localize(MARKET_TZ)
        .dt.tz_convert("UTC")
        .dt.as_unit("s")
    )

    df_out = pd.DataFrame(
        {
            "region_id": df_raw["REGION"].astype("string"),
            "timestamp_utc": ts_utc,
            "load_mw": df_raw["TOTALDEMAND"].astype(np.float64),
            "raw_interval_min": raw_interval_min,
            "source_file": df_raw["source_file"].astype("string"),
        }
    )

    dup_cnt = int(df_out.duplicated(subset=["region_id", "timestamp_utc"]).sum())
    if dup_cnt > 0:
        raise ValueError(f"原始粒度 (region_id, timestamp_utc) 存在 {dup_cnt} 筆重複列")

    print(
        f"[2/6] 時間解析與分段平移完成：0 筆 NaT，0 筆原始主鍵重複 "
        f"(30min={(raw_interval_min == 30).sum():,}, 5min={(raw_interval_min == 5).sum():,})"
    )
    return df_out


# ==========================================
# 3. 逐時聚合與分區連續 1h UTC 建格
# ==========================================
def aggregate_hourly_and_build_grid(df_intervals: pd.DataFrame) -> pd.DataFrame:
    """以 UTC 小時槽聚合為逐小時平均負載，並按各區實際營運起訖補齊連續 1h 網格。"""
    df_work = df_intervals.assign(
        hour_utc=df_intervals["timestamp_utc"].dt.floor("h")
    )

    hourly = (
        df_work.groupby(["region_id", "hour_utc"], sort=True, observed=True)
        .agg(
            load_mw=("load_mw", "mean"),
            sample_count=("load_mw", "count"),
            raw_interval_min=("raw_interval_min", "first"),
            source_file=("source_file", "first"),
        )
        .reset_index()
        .rename(columns={"hour_utc": "timestamp_utc"})
    )

    grid_frames: list[pd.DataFrame] = []
    for region_id in sorted(REGION_TZ_MAP.keys()):
        sub = hourly.loc[hourly["region_id"] == region_id]
        if sub.empty:
            continue
        start_ts = sub["timestamp_utc"].min()
        end_ts = sub["timestamp_utc"].max()
        full_hours = pd.date_range(
            start=start_ts,
            end=end_ts,
            freq="1h",
            tz="UTC",
        ).as_unit("s")

        grid = pd.DataFrame(
            {
                "region_id": pd.Series(region_id, index=range(len(full_hours)), dtype="string"),
                "timestamp_utc": full_hours,
            }
        )
        merged = pd.merge(
            grid,
            sub,
            on=["region_id", "timestamp_utc"],
            how="left",
            validate="one_to_one",
        )
        grid_frames.append(merged)

    df_grid = pd.concat(grid_frames, ignore_index=True)
    df_grid = df_grid.sort_values(["region_id", "timestamp_utc"]).reset_index(drop=True)

    # 缺值小時保留 load_mw = NaN、source_file = <NA>，數值型計數與間隔轉為 int8
    df_grid["sample_count"] = df_grid["sample_count"].fillna(0).astype(np.int8)
    expected_interval = np.where(df_grid["timestamp_utc"] < FIVE_MIN_SWITCH_UTC, 30, 5).astype(np.int8)
    df_grid["raw_interval_min"] = (
        df_grid["raw_interval_min"].fillna(pd.Series(expected_interval, index=df_grid.index)).astype(np.int8)
    )

    assert not df_grid.duplicated(subset=["region_id", "timestamp_utc"]).any(), (
        "主鍵驗證失敗：(region_id, timestamp_utc) 存在重複列"
    )
    print(f"[3/6] 逐時聚合與分區連續 1h 網格建立完成：共 {len(df_grid):,} 列")
    return df_grid


# ==========================================
# 4. 結構性完整性品質旗標（無極端值過濾）
# ==========================================
def attach_structural_quality_flags(df: pd.DataFrame) -> pd.DataFrame:
    """計算結構性缺值、預期樣本數、不完整小時旗標與向量化 quality_flag。"""
    is_missing = df["load_mw"].isna().astype(np.int8)
    expected_samples = np.where(df["timestamp_utc"] < FIVE_MIN_SWITCH_UTC, 2, 12).astype(np.int8)
    is_partial_hour = ((is_missing == 0) & (df["sample_count"] < expected_samples)).astype(np.int8)
    is_duplicate = np.zeros(len(df), dtype=np.int8)

    quality_flag = np.select(
        [is_missing == 1, is_partial_hour == 1],
        ["MISSING", "PARTIAL_HOUR"],
        default="OK",
    )

    df_out = df.assign(
        is_missing=is_missing,
        expected_samples=expected_samples,
        is_partial_hour=is_partial_hour,
        is_duplicate=is_duplicate,
        quality_flag=pd.Series(quality_flag, index=df.index, dtype="string"),
    )

    print(
        f"[4/6] 結構性完整性旗標完成：MISSING={int(is_missing.sum())}, "
        f"PARTIAL_HOUR={int(is_partial_hour.sum())}, DUPLICATE=0"
    )
    return df_out


# ==========================================
# 5. 各州民用時區、DST、外部假日／緊急停班與疫情旗標
# ==========================================
def attach_civil_calendar_and_events(
    df: pd.DataFrame,
    holidays_csv_path: Path,
    emergency_csv_path: Path,
) -> pd.DataFrame:
    """依各州民用 IANA 時區向量化產生日曆與 DST 欄位，並左連接假日、緊急停班與疫情旗標。"""
    region_parts: list[pd.DataFrame] = []

    for region_id, iana_tz in REGION_TZ_MAP.items():
        sub = df.loc[df["region_id"] == region_id].copy()
        if sub.empty:
            continue

        ts_utc = sub["timestamp_utc"]
        ts_local = ts_utc.dt.tz_convert(iana_tz)

        # 向量化計算當地與 UTC 偏移秒數（相容夏令切換雙重小時與半小時時區）
        offset_sec = (
            (ts_local.dt.tz_localize(None) - ts_utc.dt.tz_localize(None))
            .dt.total_seconds()
            .astype(np.int64)
        )
        std_offset = REGION_STD_OFFSET_SEC[region_id]
        is_dst = (offset_sec > std_offset).astype(np.int8)
        prev_offset = offset_sec.shift(1)
        is_dst_transition = ((offset_sec != prev_offset) & prev_offset.notna()).astype(np.int8)

        # 向量化產生 ISO-8601 含冒號時區偏移字串
        ts_local_iso = (
            ts_local.dt.strftime("%Y-%m-%dT%H:%M:%S%z")
            .str.replace(r"([+-]\d{2})(\d{2})$", r"\1:\2", regex=True)
            .astype("string")
        )

        day_of_week = (ts_local.dt.dayofweek + 1).astype(np.int8)
        sub = sub.assign(
            iana_tz=pd.Series(iana_tz, index=sub.index, dtype="string"),
            timestamp_local=ts_local_iso,
            local_date=ts_local.dt.strftime("%Y-%m-%d").astype("string"),
            local_hour=ts_local.dt.hour.astype(np.int8),
            day_of_week=day_of_week,
            is_weekend=day_of_week.isin([6, 7]).astype(np.int8),
            is_dst=is_dst,
            is_dst_transition=is_dst_transition,
        )
        region_parts.append(sub)

    df_cal = pd.concat(region_parts, ignore_index=True)
    df_cal = df_cal.sort_values(["region_id", "timestamp_utc"]).reset_index(drop=True)

    # 讀取並檢核外部假日表與緊急停班表主鍵唯一性
    df_hol = pd.read_csv(
        holidays_csv_path,
        usecols=["region_id", "local_date", "holiday_name"],
        dtype="string",
    )
    assert not df_hol.duplicated(subset=["region_id", "local_date"]).any(), (
        "au_public_holidays.csv 主鍵 (region_id, local_date) 存在重複"
    )

    df_em = pd.read_csv(
        emergency_csv_path,
        usecols=["region_id", "local_date", "event_category", "scope"],
        dtype="string",
    ).rename(
        columns={
            "event_category": "emergency_event_category",
            "scope": "emergency_scope",
        }
    )
    assert not df_em.duplicated(subset=["region_id", "local_date"]).any(), (
        "au_emergency_closures.csv 主鍵 (region_id, local_date) 存在重複"
    )

    df_merged = pd.merge(
        df_cal,
        df_hol,
        on=["region_id", "local_date"],
        how="left",
        validate="many_to_one",
    )
    df_merged = pd.merge(
        df_merged,
        df_em,
        on=["region_id", "local_date"],
        how="left",
        validate="many_to_one",
    )

    is_public_holiday = df_merged["holiday_name"].notna().astype(np.int8)
    is_emergency_closure = df_merged["emergency_event_category"].notna().astype(np.int8)

    # 嚴格互斥五分類 day_type（保留獨立 is_weekend / is_public_holiday / is_emergency_closure 欄位不變）
    is_weekend = df_merged["is_weekend"]
    day_type = np.select(
        [
            (is_emergency_closure == 1) & (is_public_holiday == 1),
            (is_emergency_closure == 1) & (is_public_holiday == 0),
            (is_emergency_closure == 0) & (is_public_holiday == 1),
            (is_emergency_closure == 0) & (is_public_holiday == 0) & (is_weekend == 1),
        ],
        [
            "BOTH",
            "EMERGENCY_CLOSURE",
            "PUBLIC_HOLIDAY",
            "WEEKEND",
        ],
        default="WEEKDAY",
    )

    is_covid_period = (
        (df_merged["local_date"] >= COVID_START_DATE)
        & (df_merged["local_date"] <= COVID_END_DATE)
    ).astype(np.int8)

    df_out = df_merged.assign(
        day_type=pd.Series(day_type, index=df_merged.index, dtype="string"),
        is_public_holiday=is_public_holiday,
        is_emergency_closure=is_emergency_closure,
        is_covid_period=is_covid_period,
    )

    print(
        f"[5/6] 民用時區與外部事件整合完成：is_dst={int(df_out['is_dst'].sum()):,}, "
        f"is_public_holiday={int(is_public_holiday.sum()):,}, "
        f"is_emergency_closure={int(is_emergency_closure.sum()):,}, "
        f"is_covid_period={int(is_covid_period.sum()):,}"
    )
    return df_out


# ==========================================
# 6. SHA-256 溯源欄位封裝與雙 Parquet 輸出
# ==========================================
def attach_lineage_and_export_parquets(
    df: pd.DataFrame,
    lineage: dict,
    main_output_path: Path,
    full_qc_output_path: Path,
) -> dict:
    """附上逐列 source_file_sha256 與 version，並寫出含完整 64 碼 Metadata 的雙 Parquet 檔。"""
    source_sha_map: dict[str, str] = lineage["source_file_sha256_map"]
    source_file_sha256 = df["source_file"].map(source_sha_map).astype("string")

    # 驗證非缺失列皆成功映射至 64 碼 SHA-256
    unmapped = int((df["source_file"].notna() & source_file_sha256.isna()).sum())
    if unmapped > 0:
        raise RuntimeError(f"有 {unmapped} 筆非缺失列無法映射至 source_file_sha256")

    df_full = df.assign(
        source_file_sha256=source_file_sha256,
        version=pd.Series(lineage["version_tag"], index=df.index, dtype="string"),
    )

    # 最終排序與複合主鍵唯一性斷言
    df_full = df_full.sort_values(["region_id", "timestamp_utc"]).reset_index(drop=True)
    assert not df_full.duplicated(subset=["region_id", "timestamp_utc"]).any(), (
        "最終主鍵驗證失敗：(region_id, timestamp_utc) 存在重複列"
    )

    generated_at_utc = datetime.now(timezone.utc).isoformat()
    custom_meta = {
        b"pipeline_version": str(lineage["pipeline_version"]).encode("utf-8"),
        b"master_sources_sha256": str(lineage["master_sources_sha256"]).encode("utf-8"),
        b"input_raw_parquet_sha256": str(lineage["input_raw_parquet_sha256"]).encode("utf-8"),
        b"external_holidays_sha256": str(lineage["external_holidays_sha256"]).encode("utf-8"),
        b"external_emergency_sha256": str(lineage["external_emergency_sha256"]).encode("utf-8"),
        b"generated_at_utc": generated_at_utc.encode("utf-8"),
    }

    dict_str_type = pa.dictionary(pa.int16(), pa.string())

    main_schema = pa.schema(
        [
            pa.field("region_id", dict_str_type),
            pa.field("timestamp_utc", pa.timestamp("s", tz="UTC")),
            pa.field("local_date", pa.string()),
            pa.field("local_hour", pa.int8()),
            pa.field("day_of_week", pa.int8()),
            pa.field("is_weekend", pa.int8()),
            pa.field("is_dst", pa.int8()),
            pa.field("load_mw", pa.float64()),
            pa.field("day_type", dict_str_type),
            pa.field("is_public_holiday", pa.int8()),
            pa.field("is_emergency_closure", pa.int8()),
            pa.field("is_covid_period", pa.int8()),
            pa.field("is_missing", pa.int8()),
            pa.field("quality_flag", dict_str_type),
        ]
    )

    full_qc_schema = pa.schema(
        [
            *list(main_schema),
            pa.field("iana_tz", dict_str_type),
            pa.field("timestamp_local", pa.string()),
            pa.field("raw_interval_min", pa.int8()),
            pa.field("sample_count", pa.int8()),
            pa.field("expected_samples", pa.int8()),
            pa.field("is_partial_hour", pa.int8()),
            pa.field("is_duplicate", pa.int8()),
            pa.field("is_dst_transition", pa.int8()),
            pa.field("holiday_name", dict_str_type),
            pa.field("emergency_event_category", dict_str_type),
            pa.field("emergency_scope", dict_str_type),
            pa.field("source_file", dict_str_type),
            pa.field("source_file_sha256", dict_str_type),
            pa.field("version", dict_str_type),
        ]
    )

    def _write_parquet_with_meta(df_part: pd.DataFrame, schema: pa.Schema, out_path: Path) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(df_part, schema=schema, preserve_index=False)
        merged_meta = {**(table.schema.metadata or {}), **custom_meta}
        table = table.replace_schema_metadata(merged_meta)
        pq.write_table(table, out_path, compression=PARQUET_COMPRESSION)

    _write_parquet_with_meta(df_full[MAIN_COLUMNS], main_schema, main_output_path)
    _write_parquet_with_meta(df_full[FULL_QC_COLUMNS], full_qc_schema, full_qc_output_path)

    main_mb = main_output_path.stat().st_size / (1024 * 1024)
    qc_mb = full_qc_output_path.stat().st_size / (1024 * 1024)
    print(
        f"[6/6] 雙 Parquet 寫入完成：\n"
        f"   -> 主訓練長表：{main_output_path.name} ({len(df_full):,} 列, {len(MAIN_COLUMNS)} 欄, {main_mb:.2f} MB)\n"
        f"   -> 完整稽核表：{full_qc_output_path.name} ({len(df_full):,} 列, {len(FULL_QC_COLUMNS)} 欄, {qc_mb:.2f} MB)"
    )

    return {
        "rows": int(len(df_full)),
        "main_size_mb": round(main_mb, 4),
        "full_qc_size_mb": round(qc_mb, 4),
        "version_tag": lineage["version_tag"],
        "generated_at_utc": generated_at_utc,
    }
