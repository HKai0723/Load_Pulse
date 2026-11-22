import argparse
import hashlib
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "data" / "raw" / "Australia_AEMO"
MANIFEST_PATH = OUT_DIR / "raw_manifest.json"

BASE_URL = "https://www.aemo.com.au/aemo/data/nem/priceanddemand/"
ACTIVE_REGIONS = ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"]
DEFAULT_START_YM = "199812"
DEFAULT_END_YM = "202611"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,text/plain,*/*",
}


def generate_ym_list(start_ym: str, end_ym: str) -> list[str]:
    """產生從 start_ym 到 end_ym 的連續 YYYYMM 字串清單。"""
    sy, sm = int(start_ym[:4]), int(start_ym[4:6])
    ey, em = int(end_ym[:4]), int(end_ym[4:6])
    yms = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        yms.append(f"{y:04d}{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return yms


def compute_sha256(file_path: Path) -> str:
    """計算本地檔案之 SHA-256 雜湊指紋。"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def count_csv_rows(file_path: Path) -> int:
    """快速計算 CSV 資料筆數（扣除標題列）。"""
    with open(file_path, "rb") as f:
        return max(0, sum(1 for _ in f) - 1)


def download_with_retry(
    session: requests.Session,
    url: str,
    out_file: Path,
    max_retries: int = 4,
) -> tuple[str, str]:
    """具備指數退避重試與原子寫入 (.tmp -> .csv) 的下載函式。"""
    tmp_file = out_file.with_suffix(".csv.tmp")
    backoff_seconds = [5, 15, 30, 60]

    for attempt in range(max_retries + 1):
        try:
            resp = session.get(url, timeout=30)

            # 尚未併網月份（例如 TAS1 於 2005-05 併網前）
            if resp.status_code == 404:
                return "not_found", "HTTP 404"

            if resp.status_code in {429, 500, 502, 503, 504}:
                if attempt < max_retries:
                    wait = backoff_seconds[attempt] + random.uniform(0.5, 2.0)
                    print(f"   [HTTP {resp.status_code}] 等待 {wait:.1f}s 後第 {attempt + 1} 次重試...")
                    time.sleep(wait)
                    continue
                return "failed", f"HTTP {resp.status_code}"

            resp.raise_for_status()

            first_line = resp.content.split(b"\n", 1)[0].decode("utf-8", errors="ignore").strip()
            if not first_line.startswith("REGION,"):
                return "failed", f"非預期內容格式: {first_line[:40]}"

            tmp_file.write_bytes(resp.content)
            tmp_file.replace(out_file)
            return "downloaded", "OK"

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if tmp_file.exists():
                tmp_file.unlink(missing_ok=True)
            if attempt < max_retries:
                wait = backoff_seconds[attempt] + random.uniform(0.5, 2.0)
                print(f"   [連線逾時/中斷] 等待 {wait:.1f}s 後第 {attempt + 1} 次重試...")
                time.sleep(wait)
            else:
                return "failed", type(e).__name__
        except Exception as e:
            if tmp_file.exists():
                tmp_file.unlink(missing_ok=True)
            return "failed", f"{type(e).__name__}: {e}"

    return "failed", "未知錯誤"


def save_manifest(
    records: dict,
    unavailable: list,
    failed: list,
    start_ym: str,
    end_ym: str,
) -> None:
    """將原始快照清單與 SHA-256 指紋寫入 raw_manifest.json。"""
    manifest = {
        "source_id": "AEMO_NEM_PRICE_AND_DEMAND",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_range": {"start_ym": start_ym, "end_ym": end_ym},
        "summary": {
            "total_valid_files": len(records),
            "unavailable_404_count": len(unavailable),
            "failed_count": len(failed),
        },
        "files": records,
        "unavailable_periods": unavailable,
        "failed_periods": failed,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def fetch_australia_history(
    regions: list[str] = ACTIVE_REGIONS,
    start_ym: str = DEFAULT_START_YM,
    end_ym: str = DEFAULT_END_YM,
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ym_list = generate_ym_list(start_ym, end_ym)

    existing_files = {}
    if MANIFEST_PATH.exists():
        try:
            existing_files = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")).get("files", {})
        except Exception:
            existing_files = {}

    file_records: dict = {}
    unavailable_list: list = []
    failed_list: list = []

    print(f"開始擷取澳洲 AEMO NEM 歷史資料 ({start_ym} ~ {end_ym}，共 {len(ym_list)} 個月 × {len(regions)} 區)")
    print(f"儲存路徑：{OUT_DIR}\n")

    with requests.Session() as session:
        session.headers.update(HEADERS)

        for region in regions:
            (OUT_DIR / region).mkdir(parents=True, exist_ok=True)
            dl_cnt = cache_cnt = na_cnt = 0

            for idx, ym in enumerate(ym_list, start=1):
                rel_key = f"{region}/AU_AEMO_{region}_RAW_{ym}.csv"
                out_file = OUT_DIR / rel_key

                # 斷點續傳：本地已存在且非空則直接跳過
                if out_file.exists() and out_file.stat().st_size > 0:
                    cache_cnt += 1
                    prev = existing_files.get(rel_key, {})
                    file_records[rel_key] = {
                        "region": region,
                        "ym": ym,
                        "rows": prev.get("rows") or count_csv_rows(out_file),
                        "bytes": out_file.stat().st_size,
                        "sha256": prev.get("sha256") or compute_sha256(out_file),
                        "downloaded_at_utc": prev.get("downloaded_at_utc", "cached_local"),
                    }
                    continue

                url = f"{BASE_URL}PRICE_AND_DEMAND_{ym}_{region}.csv"
                status, msg = download_with_retry(session, url, out_file)

                if status == "downloaded":
                    dl_cnt += 1
                    file_records[rel_key] = {
                        "region": region,
                        "ym": ym,
                        "rows": count_csv_rows(out_file),
                        "bytes": out_file.stat().st_size,
                        "sha256": compute_sha256(out_file),
                        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
                    }
                elif status == "not_found":
                    na_cnt += 1
                    unavailable_list.append({"region": region, "ym": ym})
                else:
                    failed_list.append({"region": region, "ym": ym, "reason": msg})
                    print(f"   [失敗] {region} {ym}: {msg}")

                if idx % 24 == 0 or idx == len(ym_list):
                    print(
                        f"[{region}] {idx}/{len(ym_list)} ({ym}) | "
                        f"新下載: {dl_cnt} | 快取: {cache_cnt} | 尚未併網(404): {na_cnt}"
                    )

                time.sleep(random.uniform(0.45, 0.95))

            save_manifest(file_records, unavailable_list, failed_list, start_ym, end_ym)

    print("\n" + "=" * 65)
    print(f"擷取完成！有效檔案: {len(file_records)} | 失敗: {len(failed_list)}")
    print(f"溯源雜湊清單：{MANIFEST_PATH}")
    print("=" * 65)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AEMO NEM 歷史電力負載批次擷取腳本")
    parser.add_argument("--start", default=DEFAULT_START_YM, help="起始年月 YYYYMM (預設: 199812)")
    parser.add_argument("--end", default=DEFAULT_END_YM, help="結束年月 YYYYMM (預設: 202611)")
    parser.add_argument("--regions", nargs="+", default=ACTIVE_REGIONS, help="指定調度區代碼清單")
    args = parser.parse_args()

    fetch_australia_history(regions=args.regions, start_ym=args.start, end_ym=args.end)