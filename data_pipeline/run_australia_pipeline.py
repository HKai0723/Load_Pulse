"""澳洲 AEMO NEM 五大調度區全歷史 (1998–2026) 逐小時長表清洗與品質檢核管線入口。

輸入（唯讀，啟動前強制通過 raw_bundle_manifest.json SHA-256 驗真）：
- data/processed/raw_bundle_manifest.json
- data/processed/AU_AEMO_NEM_raw_1998_2026.parquet
- data/external/au_public_holidays.csv
- data/external/au_emergency_closures.csv

輸出（僅輸出以下兩份 ZSTD Parquet，不匯出任何 CSV）：
- data/processed/AU_AEMO_NEM_hourly_1998_2026.parquet (14 欄主訓練長表)
- data/processed/AU_AEMO_NEM_hourly_1998_2026_full_qc.parquet (28 欄完整稽核溯源長表)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

PIPELINE_DIR = Path(__file__).resolve().parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from core_pipeline import (
    PIPELINE_VERSION,
    aggregate_hourly_and_build_grid,
    attach_civil_calendar_and_events,
    attach_lineage_and_export_parquets,
    attach_structural_quality_flags,
    parse_and_shift_timestamps,
    verify_and_load_raw_parquet,
)

PROJECT_ROOT = PIPELINE_DIR.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
EXTERNAL_DIR = PROJECT_ROOT / "data" / "external"

BUNDLE_MANIFEST_PATH = PROCESSED_DIR / "raw_bundle_manifest.json"
RAW_PARQUET_PATH = PROCESSED_DIR / "AU_AEMO_NEM_raw_1998_2026.parquet"
HOLIDAYS_CSV_PATH = EXTERNAL_DIR / "au_public_holidays.csv"
EMERGENCY_CSV_PATH = EXTERNAL_DIR / "au_emergency_closures.csv"

MAIN_OUTPUT_PATH = PROCESSED_DIR / "AU_AEMO_NEM_hourly_1998_2026.parquet"
FULL_QC_OUTPUT_PATH = PROCESSED_DIR / "AU_AEMO_NEM_hourly_1998_2026_full_qc.parquet"


def run_australia_full_history_pipeline() -> dict:
    """執行澳洲 AEMO NEM 全歷史 (1998–2026) 逐小時長表清洗管線。"""
    t0 = time.perf_counter()
    print("=" * 72)
    print(f"LoadPulse 澳洲全歷史清洗管線 v{PIPELINE_VERSION}")
    print(f"專案根目錄：{PROJECT_ROOT}")
    print("=" * 72)

    df_raw, lineage = verify_and_load_raw_parquet(
        project_root=PROJECT_ROOT,
        bundle_manifest_path=BUNDLE_MANIFEST_PATH,
        raw_parquet_path=RAW_PARQUET_PATH,
        holidays_csv_path=HOLIDAYS_CSV_PATH,
        emergency_csv_path=EMERGENCY_CSV_PATH,
    )

    df_intervals = parse_and_shift_timestamps(df_raw)
    df_grid = aggregate_hourly_and_build_grid(df_intervals)
    df_flagged = attach_structural_quality_flags(df_grid)
    df_enriched = attach_civil_calendar_and_events(
        df=df_flagged,
        holidays_csv_path=HOLIDAYS_CSV_PATH,
        emergency_csv_path=EMERGENCY_CSV_PATH,
    )

    export_stats = attach_lineage_and_export_parquets(
        df=df_enriched,
        lineage=lineage,
        main_output_path=MAIN_OUTPUT_PATH,
        full_qc_output_path=FULL_QC_OUTPUT_PATH,
    )

    elapsed = time.perf_counter() - t0
    summary = (
        df_enriched.groupby("region_id", sort=True)
        .agg(
            rows=("timestamp_utc", "count"),
            missing=("is_missing", "sum"),
            partial=("is_partial_hour", "sum"),
            dst_hours=("is_dst", "sum"),
            holidays=("is_public_holiday", "sum"),
            emergency=("is_emergency_closure", "sum"),
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

    print("\n" + "-" * 72)
    print(summary.to_string(index=False))
    day_type_counts = df_enriched["day_type"].value_counts().to_dict()
    print("-" * 72)
    print(f"day_type 五分類分佈：{day_type_counts} (合計={sum(day_type_counts.values()):,})")
    print(f"管線總耗時：{elapsed:.2f} 秒 | 版本標籤：{export_stats['version_tag']}")
    print("=" * 72)
    export_stats["elapsed_sec"] = round(elapsed, 2)
    return export_stats


if __name__ == "__main__":
    run_australia_full_history_pipeline()
