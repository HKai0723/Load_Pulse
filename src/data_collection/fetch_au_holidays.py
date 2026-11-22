"""擷取澳洲 NEM 五大調度區 (1998–2026) 靜態國定假日表。

使用 `python-holidays` 套件產生各州國定假日清單，並依 AEMO 歷史資料涵蓋期間裁切，
輸出欄位與既有緊急停班表 (`data/external/au_emergency_*.csv`) 完全一致。
"""

from datetime import date
from pathlib import Path

import holidays
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXTERNAL_DIR = PROJECT_ROOT / "data" / "external"
OUTPUT_PATH = EXTERNAL_DIR / "au_public_holidays.csv"

REGION_SUBDIV_MAP: dict[str, str] = {
    "NSW1": "NSW",
    "QLD1": "QLD",
    "SA1": "SA",
    "TAS1": "TAS",
    "VIC1": "VIC",
}

GLOBAL_START_DATE = date(1998, 12, 1)
GLOBAL_END_DATE = date(2026, 11, 30)
REGION_START_OVERRIDES: dict[str, date] = {
    "TAS1": date(2005, 5, 1),
}

OUTPUT_COLUMNS = [
    "region_id",
    "local_date",
    "day_type",
    "holiday_name",
    "scope",
    "event_category",
    "source_url",
    "notes",
]


def build_au_public_holidays() -> pd.DataFrame:
    """建立 1998-12-01 至 2026-11-30 澳洲五區國定假日靜態表。"""
    years = range(GLOBAL_START_DATE.year, GLOBAL_END_DATE.year + 1)
    lib_version = getattr(holidays, "__version__", "unknown")
    rows: list[dict[str, str]] = []

    for region_id, subdiv in REGION_SUBDIV_MAP.items():
        start_dt = max(GLOBAL_START_DATE, REGION_START_OVERRIDES.get(region_id, GLOBAL_START_DATE))
        end_dt = GLOBAL_END_DATE

        au_cal = holidays.country_holidays("AU", subdiv=subdiv, years=years)
        for dt in sorted(au_cal.keys()):
            if dt < start_dt or dt > end_dt:
                continue

            names = au_cal.get_list(dt)
            merged_name = "; ".join(dict.fromkeys(n.strip() for n in names if n and n.strip()))

            rows.append(
                {
                    "region_id": region_id,
                    "local_date": dt.isoformat(),
                    "day_type": "PUBLIC_HOLIDAY",
                    "holiday_name": merged_name,
                    "scope": "STATEWIDE",
                    "event_category": "PUBLIC_HOLIDAY",
                    "source_url": "python-holidays",
                    "notes": f"python-holidays {lib_version} (AU-{subdiv})",
                }
            )

    df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)

    # 若同一 (region_id, local_date) 仍有多筆紀錄，合併 holiday_name 確保主鍵唯一
    df = (
        df.groupby(["region_id", "local_date"], as_index=False, sort=True)
        .agg(
            {
                "day_type": "first",
                "holiday_name": lambda s: "; ".join(dict.fromkeys(x for x in s if x)),
                "scope": "first",
                "event_category": "first",
                "source_url": "first",
                "notes": "first",
            }
        )[OUTPUT_COLUMNS]
        .sort_values(["region_id", "local_date"])
        .reset_index(drop=True)
    )

    assert not df.duplicated(subset=["region_id", "local_date"]).any(), (
        "主鍵驗證失敗：(region_id, local_date) 存在重複值"
    )
    return df


def main() -> None:
    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    df = build_au_public_holidays()
    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")

    print(f"已輸出澳洲國定假日靜態表：{OUTPUT_PATH}")
    print(f"總筆數：{len(df)}")
    print("各區筆數：")
    for region_id, cnt in df["region_id"].value_counts().sort_index().items():
        min_d = df.loc[df["region_id"] == region_id, "local_date"].min()
        max_d = df.loc[df["region_id"] == region_id, "local_date"].max()
        print(f"  - {region_id}: {cnt} ({min_d} ~ {max_d})")


if __name__ == "__main__":
    main()
