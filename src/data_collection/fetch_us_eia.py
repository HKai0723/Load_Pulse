import os
import json
import time
import requests
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "data" / "raw" / "US_EIA_Demand"
ENV_FILE = PROJECT_ROOT / ".env"


def load_api_key(key_name: str) -> str | None:
    if os.getenv(key_name):
        return os.getenv(key_name)

    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == key_name:
                return v.strip().strip('"').strip("'")
    return None


def fetch_us_eia_202101():
    api_key = load_api_key("EIA_API_KEY")
    if not api_key:
        raise EnvironmentError(f"找不到 EIA_API_KEY，請確認 {ENV_FILE} 已設定金鑰。")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUT_DIR / "US_EIA_SubBA_RAW_202101.csv"

    url = f"https://api.eia.gov/v2/electricity/rto/region-sub-ba-data/data/?api_key={api_key}"
    all_records = []
    offset = 0
    page_size = 5000

    while True:
        x_params = {
            "frequency": "hourly",
            "data": ["value"],
            "start": "2021-01-01T00",
            "end": "2021-02-01T00",
            "sort": [{"column": "period", "direction": "asc"}],
            "offset": offset,
            "length": page_size,
        }
        resp = requests.get(url, headers={"X-Params": json.dumps(x_params)}, timeout=30)
        resp.raise_for_status()

        res_body = resp.json().get("response", {})
        records = res_body.get("data", [])
        total_rows = int(res_body.get("total", 0))

        all_records.extend(records)
        print(f"已取得 {len(all_records):,} / {total_rows:,} 筆...")

        if len(records) < page_size or len(all_records) >= total_rows:
            break
        offset += page_size
        time.sleep(0.3)

    if all_records:
        df = pd.DataFrame(all_records)
        df.to_csv(out_file, index=False, encoding="utf-8-sig")
        print(f"美國 EIA 抓取完成：共 {len(df):,} 筆 -> {out_file}")


if __name__ == "__main__":
    fetch_us_eia_202101()