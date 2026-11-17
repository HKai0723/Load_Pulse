import requests
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "data" / "raw" / "Australia_AEMO"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def fetch_australia_202101():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    regions = ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"]

    for region in regions:
        url = f"https://www.aemo.com.au/aemo/data/nem/priceanddemand/PRICE_AND_DEMAND_202101_{region}.csv"
        out_file = OUT_DIR / f"AU_AEMO_{region}_RAW_202101.csv"

        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        out_file.write_bytes(resp.content)

        df = pd.read_csv(out_file)
        print(f"澳洲 [{region}] 抓取完成：共 {len(df):,} 筆 -> {out_file.name}")


if __name__ == "__main__":
    fetch_australia_202101()