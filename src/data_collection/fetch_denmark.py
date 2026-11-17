import requests
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "data" / "raw" / "Denmark_Energinet"


def fetch_denmark_202101():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUT_DIR / "DK_ConsumptionCategory_RAW_202101.csv"

    url = "https://api.energidataservice.dk/dataset/ConsumptionConsumerCategoryHour"
    params = {
        "start": "2021-01-01T00:00",
        "end": "2021-02-01T00:00",
        "limit": 0,
    }

    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    records = resp.json().get("records", [])

    if records:
        df = pd.DataFrame(records)
        df.to_csv(out_file, index=False, encoding="utf-8-sig")
        print(f"丹麥抓取完成：共 {len(df):,} 筆 -> {out_file}")


if __name__ == "__main__":
    fetch_denmark_202101()