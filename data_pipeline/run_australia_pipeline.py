"""澳洲 AEMO NEM 五大調度區全歷史 (1999–2026) 逐小時長表清洗與按年分表 SQLite 建庫入口。

輸入（唯讀，啟動前強制通過 raw_bundle_manifest.json SHA-256 驗真）：
- data/processed/raw_bundle_manifest.json
- data/processed/AU_AEMO_NEM_raw_1998_2026.parquet
- data/external/au_public_holidays.csv

輸出：
- data/processed/AU_AEMO_NEM_hourly_1999_2026.parquet (13 欄主訓練長表)
- data/processed/AU_AEMO_NEM_hourly_1999_2026_full_qc.parquet (25 欄完整稽核溯源長表)
- data/processed/AU_AEMO_NEM_hourly_1999_2026.db (28 張按 UTC 年份分表 nem_1999..nem_2026 之 SQLite 資料庫)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from core_pipeline import (
    PIPELINE_VERSION,
    aggregate_hourly_and_build_grid,
    attach_civil_calendar_and_holidays,
    attach_lineage_and_export_parquets,
    attach_structural_quality_flags,
    export_annual_sqlite_db,
    parse_and_shift_timestamps,
    verify_and_load_raw_parquet,
)

PROJECT_ROOT = PIPELINE_DIR.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
EXTERNAL_DIR = PROJECT_ROOT / "data" / "external"

BUNDLE_MANIFEST_PATH = PROCESSED_DIR / "raw_bundle_manifest.json"
RAW_PARQUET_PATH = PROCESSED_DIR / "AU_AEMO_NEM_raw_1998_2026.parquet"
HOLIDAYS_CSV_PATH = EXTERNAL_DIR / "au_public_holidays.csv"

MAIN_OUTPUT_PATH = PROCESSED_DIR / "AU_AEMO_NEM_hourly_1999_2026.parquet"
FULL_QC_OUTPUT_PATH = PROCESSED_DIR / "AU_AEMO_NEM_hourly_1999_2026_full_qc.parquet"
SQLITE_OUTPUT_PATH = PROCESSED_DIR / "AU_AEMO_NEM_hourly_1999_2026.db"


def run_australia_full_history_pipeline() -> dict:
    """執行澳洲 AEMO NEM (1999–2026 / TAS1 2006–2026) 逐小時長表清洗與 SQLite 分表輸出。"""
    t0 = time.perf_counter()
    print("=" * 74)
    print(f"LoadPulse 澳洲全歷史清洗管線 v{PIPELINE_VERSION}")
    print(f"專案根目錄：{PROJECT_ROOT}")
    print("=" * 74)

    df_raw, lineage = verify_and_load_raw_parquet(
        project_root=PROJECT_ROOT,
        bundle_manifest_path=BUNDLE_MANIFEST_PATH,
        raw_parquet_path=RAW_PARQUET_PATH,
        holidays_csv_path=HOLIDAYS_CSV_PATH,
    )

    df_intervals = parse_and_shift_timestamps(df_raw)
    df_grid = aggregate_hourly_and_build_grid(df_intervals)
    df_flagged = attach_structural_quality_flags(df_grid)
    df_enriched = attach_civil_calendar_and_holidays(
        df=df_flagged,
        holidays_csv_path=HOLIDAYS_CSV_PATH,
    )

    df_full, export_stats = attach_lineage_and_export_parquets(
        df=df_enriched,
        lineage=lineage,
        main_output_path=MAIN_OUTPUT_PATH,
        full_qc_output_path=FULL_QC_OUTPUT_PATH,
    )

    sqlite_stats = export_annual_sqlite_db(
        df_full=df_full,
        sqlite_output_path=SQLITE_OUTPUT_PATH,
    )
    export_stats.update(sqlite_stats)

    elapsed = time.perf_counter() - t0
    summary = (
        df_full.groupby("region_id", sort=True)
        .agg(
            start_utc=("timestamp_utc", "min"),
            end_utc=("timestamp_utc", "max"),
            rows=("timestamp_utc", "count"),
            missing=("is_missing", "sum"),
            partial=("is_partial_hour", "sum"),
            dst_hours=("is_dst", "sum"),
            holidays=("is_public_holiday", "sum"),
            covid=("is_covid_period", "sum"),
            min_mw=("load_mw", "min"),
            mean_mw=("load_mw", "mean"),
            max_mw=("load_mw", "max"),
        )
        .reset_index()
    )
    summary["min_mw"] = summary["min_mw"].round(2)
    summary["mean_mw"] = summary["mean_mw"].round(2)
    summary["max_mw"] = summary["max_mw"].round(2)

    print("\n" + "-" * 74)
    print(summary.to_string(index=False))
    day_type_counts = df_full["day_type"].value_counts().to_dict()
    print("-" * 74)
    print(f"day_type 純三分類分佈：{day_type_counts} (合計={sum(day_type_counts.values()):,})")
    print(f"管線總耗時：{elapsed:.2f} 秒 | 版本標籤：{export_stats['version_tag']}")
    print("=" * 74)
    export_stats["elapsed_sec"] = round(elapsed, 2)
    return export_stats


if __name__ == "__main__":
    run_australia_full_history_pipeline()
