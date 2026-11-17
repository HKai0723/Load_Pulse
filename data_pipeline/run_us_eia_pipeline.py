import pandas as pd
from pathlib import Path
from core_pipeline import (
    PIPELINE_VERSION,
    load_raw_data,
    normalize_timestamp,
    validate_frequency,
    detect_missing_hours,
    detect_duplicates,
    validate_load_values,
    generate_quality_flags,
    resample_hourly,
    generate_calendar_features,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "US_EIA_Demand" / "US_EIA_SubBA_RAW_202101.csv"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

# 全美跨越多個時區，統一以 UTC 作為基準時間軸
BASE_TZ = "UTC"
START_UTC = "2021-01-01T00:00:00"
END_UTC = "2021-01-31T23:00:00"


def clean_single_ba(df_ba: pd.DataFrame, ba_code: str) -> tuple[pd.DataFrame, dict]:
    """針對單一美國一級調度區 (parent BA) 執行彙總與標準化品質檢核。"""
    subba_count = df_ba["subba"].nunique() if "subba" in df_ba.columns else 1

    df_agg = (
        df_ba.groupby("period", as_index=False)
        .agg(
            raw_timestamp=("period", "first"),
            load_mw=("value", lambda s: s.sum(min_count=1)),
        )
    )
    df_agg["period_utc"] = pd.to_datetime(df_agg["period"], utc=True)

    df_norm = normalize_timestamp(
        df_agg,
        utc_col="period_utc",
        local_tz=BASE_TZ,
        raw_ts_col="raw_timestamp",
    )

    validate_frequency(df_norm, expected_freq="1h")
    df_dedup = detect_duplicates(df_norm)
    ts_map = df_dedup[["timestamp_utc", "raw_timestamp", "is_duplicate"]].drop_duplicates("timestamp_utc")

    df_hourly = resample_hourly(df_dedup, value_col="load_mw", unit_type="power_mw")
    df_hourly = pd.merge(df_hourly, ts_map, on="timestamp_utc", how="left")

    df_complete = detect_missing_hours(
        df_hourly,
        start_utc=START_UTC,
        end_utc=END_UTC,
        local_tz=BASE_TZ,
    )
    df_complete["is_duplicate"] = df_complete["is_duplicate"].fillna(0).astype(int)

    # 涵蓋大型聯網 (如 PJM/MISO 可達 100,000+ MW)，上限設為 200,000 MW
    df_validated = validate_load_values(df_complete, min_valid_mw=100.0, max_valid_mw=200000.0)
    df_flagged = generate_quality_flags(df_validated, is_source_revised=False)
    df_final = generate_calendar_features(df_flagged)

    summary = {
        "BA": ba_code,
        "subba_cnt": subba_count,
        "raw_rows": len(df_ba),
        "hourly_rows": len(df_final),
        "missing": int(df_final["is_missing"].sum()),
        "outliers": int(df_final["is_suspected_outlier"].sum()),
        "min_mw": round(df_final["load_mw"].min(), 2),
        "mean_mw": round(df_final["load_mw"].mean(), 2),
        "max_mw": round(df_final["load_mw"].max(), 2),
    }
    return df_final, summary


def run_all_us_eia_202101():
    print(f"專案根目錄：{PROJECT_ROOT}\n")

    df_raw, lineage = load_raw_data(
        file_path=RAW_FILE,
        source_name="EIA_930_SUBBA_ALL_REGIONS",
    )

    required_cols = {"period", "parent", "value"}
    if not required_cols.issubset(df_raw.columns):
        raise KeyError(f"原始檔案缺少必要欄位，目前欄位：{df_raw.columns.tolist()}")

    df_raw["value"] = pd.to_numeric(df_raw["value"], errors="coerce")
    ba_codes = sorted(df_raw["parent"].dropna().unique().tolist())
    print(f"\n共偵測到 {len(ba_codes)} 個美國一級調度區 (parent BA)：{ba_codes}")

    ba_dfs: dict[str, pd.DataFrame] = {}
    summaries = []

    for ba in ba_codes:
        print(f"\n{'=' * 55}")
        print(f"處理美國 EIA 調度區：{ba}")
        print(f"{'=' * 55}")
        df_sub = df_raw[df_raw["parent"] == ba].copy()
        df_cleaned, stat = clean_single_ba(df_sub, ba)
        ba_dfs[ba] = df_cleaned
        summaries.append(stat)

    # 以首個調度區建立唯一 UTC 主鍵與共用日曆基底表
    base_df = ba_dfs[ba_codes[0]][
        ["timestamp_utc", "timestamp_local", "iana_tz", "hour", "day_of_week", "is_weekend"]
    ].copy()

    clean_unified = base_df[["timestamp_utc", "hour", "day_of_week", "is_weekend"]].copy()
    full_qc_unified = base_df.copy()

    qc_flag_cols = [
        "is_missing",
        "is_duplicate",
        "is_dst_transition",
        "is_imputed",
        "is_suspected_outlier",
        "is_source_revised",
        "quality_flag",
    ]

    # 依 timestamp_utc 一對一橫向合併各調度區欄位
    for ba in ba_codes:
        df_b = ba_dfs[ba].copy()
        df_b["load_mw"] = df_b["load_mw"].round(3)

        sub_clean = df_b[["timestamp_utc", "load_mw", "quality_flag"]].rename(
            columns={
                "load_mw": f"{ba}_load_mw",
                "quality_flag": f"{ba}_quality_flag",
            }
        )
        clean_unified = pd.merge(
            clean_unified, sub_clean, on="timestamp_utc", how="outer", validate="one_to_one"
        )

        rename_map = {"raw_timestamp": f"{ba}_raw_timestamp", "load_mw": f"{ba}_load_mw"}
        for col in qc_flag_cols:
            rename_map[col] = f"{ba}_{col}"

        sub_qc = df_b[["timestamp_utc", "raw_timestamp", "load_mw"] + qc_flag_cols].rename(columns=rename_map)
        full_qc_unified = pd.merge(
            full_qc_unified, sub_qc, on="timestamp_utc", how="outer", validate="one_to_one"
        )

    clean_unified = clean_unified.sort_values("timestamp_utc").reset_index(drop=True)
    full_qc_unified = full_qc_unified.sort_values("timestamp_utc").reset_index(drop=True)
    assert clean_unified["timestamp_utc"].is_unique, "主鍵驗證失敗：timestamp_utc 存在重複值"

    clean_unified["timestamp_utc"] = clean_unified["timestamp_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    full_qc_unified["timestamp_utc"] = full_qc_unified["timestamp_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    full_qc_unified["timestamp_local"] = full_qc_unified["timestamp_local"].apply(lambda ts: ts.isoformat())

    full_qc_unified["source_name"] = "EIA_930_SUBBA_ALL_REGIONS"
    full_qc_unified["pipeline_version"] = PIPELINE_VERSION

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    clean_out = PROCESSED_DIR / "US_EIA_ALL_hourly_202101.csv"
    full_qc_out = PROCESSED_DIR / "US_EIA_ALL_hourly_202101_full_qc.csv"

    clean_unified.to_csv(clean_out, index=False, encoding="utf-8-sig")
    full_qc_unified.to_csv(full_qc_out, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 85)
    print("美國聯邦 EIA 全區調度網 (2021-01) 統一寬表輸出完成")
    print("=" * 85)
    print(f"• 標準統一檔：{clean_out} ({len(clean_unified)} 筆, 共 {len(clean_unified.columns)} 欄, 唯一 PK: timestamp_utc)")
    print(f"• 完整稽核檔：{full_qc_out}")
    print("-" * 85)
    print(pd.DataFrame(summaries).to_string(index=False))
    print("=" * 85)


if __name__ == "__main__":
    run_all_us_eia_202101()