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
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "Australia_AEMO"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

REGIONS = ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"]
LOCAL_TZ = "Australia/Brisbane"

START_UTC = pd.Timestamp("2021-01-01 00:00:00", tz=LOCAL_TZ).tz_convert("UTC").isoformat()
END_UTC = pd.Timestamp("2021-01-31 23:00:00", tz=LOCAL_TZ).tz_convert("UTC").isoformat()


def clean_single_region(region: str) -> tuple[pd.DataFrame, dict]:
    """執行單一調度區之標準化清洗與品質檢核，回傳清洗後 DataFrame 與摘要資訊。"""
    raw_file = RAW_DIR / f"AU_AEMO_{region}_RAW_202101.csv"

    df_raw, lineage = load_raw_data(
        file_path=raw_file,
        source_name=f"AEMO_NEM_PRICE_AND_DEMAND_{region}",
    )

    # 將 Interval-Ending 結算時間轉為 Interval-Beginning 當地時間
    dt_end_local = pd.to_datetime(df_raw["SETTLEMENTDATE"])
    interval = dt_end_local.diff().dropna().mode().iloc[0]
    df_raw["interval_start_local"] = (dt_end_local - interval).dt.tz_localize(LOCAL_TZ)

    df_norm = normalize_timestamp(
        df_raw,
        utc_col="interval_start_local",
        local_tz=LOCAL_TZ,
        raw_ts_col="SETTLEMENTDATE",
    )

    validate_frequency(df_norm, expected_freq="30min")
    df_dedup = detect_duplicates(df_norm)

    hourly_meta = (
        df_dedup.set_index("timestamp_utc")
        .resample("1h")
        .agg(
            raw_timestamp=("raw_timestamp", "first"),
            is_duplicate=("is_duplicate", "max"),
        )
        .reset_index()
    )

    df_hourly = resample_hourly(df_dedup, value_col="TOTALDEMAND", unit_type="power_mw")
    df_hourly = pd.merge(df_hourly, hourly_meta, on="timestamp_utc", how="left")

    df_complete = detect_missing_hours(
        df_hourly,
        start_utc=START_UTC,
        end_utc=END_UTC,
        local_tz=LOCAL_TZ,
    )
    df_complete["is_duplicate"] = df_complete["is_duplicate"].fillna(0).astype(int)

    df_validated = validate_load_values(df_complete, min_valid_mw=100.0, max_valid_mw=20000.0)
    df_flagged = generate_quality_flags(df_validated, is_source_revised=False)
    df_final = generate_calendar_features(df_flagged)

    summary = {
        "region": region,
        "raw_rows": lineage["raw_row_count"],
        "hourly_rows": len(df_final),
        "missing": int(df_final["is_missing"].sum()),
        "outliers": int(df_final["is_suspected_outlier"].sum()),
        "min_mw": round(df_final["load_mw"].min(), 2),
        "mean_mw": round(df_final["load_mw"].mean(), 2),
        "max_mw": round(df_final["load_mw"].max(), 2),
    }
    return df_final, summary


def run_unified_australia_202101():
    print(f"專案根目錄：{PROJECT_ROOT}")
    region_dfs: dict[str, pd.DataFrame] = {}
    summaries = []

    for region in REGIONS:
        print(f"\n{'=' * 55}")
        print(f"處理澳洲 AEMO 調度區：{region}")
        print(f"{'=' * 55}")
        df_reg, stat = clean_single_region(region)
        region_dfs[region] = df_reg
        summaries.append(stat)

    # 以首個調度區建立唯一 UTC 主鍵與共用日曆基底表
    base_df = region_dfs[REGIONS[0]][
        ["timestamp_utc", "timestamp_local", "iana_tz", "hour", "day_of_week", "is_weekend"]
    ].copy()

    clean_unified = base_df[["timestamp_utc", "timestamp_local", "hour", "day_of_week", "is_weekend"]].copy()
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

    # 依 timestamp_utc 一對一橫向合併五州欄位
    for region in REGIONS:
        df_r = region_dfs[region].copy()
        df_r["load_mw"] = df_r["load_mw"].round(3)

        # 標準檔僅保留各州負載與綜合品質旗標
        sub_clean = df_r[["timestamp_utc", "load_mw", "quality_flag"]].rename(
            columns={
                "load_mw": f"{region}_load_mw",
                "quality_flag": f"{region}_quality_flag",
            }
        )
        clean_unified = pd.merge(
            clean_unified, sub_clean, on="timestamp_utc", how="outer", validate="one_to_one"
        )

        # 完整稽核檔保留原始時間戳記與所有品質旗標明細
        rename_map = {"raw_timestamp": f"{region}_raw_timestamp", "load_mw": f"{region}_load_mw"}
        for col in qc_flag_cols:
            rename_map[col] = f"{region}_{col}"

        sub_qc = df_r[["timestamp_utc", "raw_timestamp", "load_mw"] + qc_flag_cols].rename(columns=rename_map)
        full_qc_unified = pd.merge(
            full_qc_unified, sub_qc, on="timestamp_utc", how="outer", validate="one_to_one"
        )

    # 排序並驗證 timestamp_utc 為唯一主鍵
    clean_unified = clean_unified.sort_values("timestamp_utc").reset_index(drop=True)
    full_qc_unified = full_qc_unified.sort_values("timestamp_utc").reset_index(drop=True)
    assert clean_unified["timestamp_utc"].is_unique, "主鍵驗證失敗：timestamp_utc 存在重複值"

    # 格式化時間戳記字串
    for df_out in (clean_unified, full_qc_unified):
        df_out["timestamp_utc"] = df_out["timestamp_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        df_out["timestamp_local"] = df_out["timestamp_local"].apply(lambda ts: ts.isoformat())

    full_qc_unified["source_name"] = "AEMO_NEM_PRICE_AND_DEMAND_ALL_REGIONS"
    full_qc_unified["pipeline_version"] = PIPELINE_VERSION

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    clean_out = PROCESSED_DIR / "AU_AEMO_NEM_hourly_202101.csv"
    full_qc_out = PROCESSED_DIR / "AU_AEMO_NEM_hourly_202101_full_qc.csv"

    clean_unified.to_csv(clean_out, index=False, encoding="utf-8-sig")
    full_qc_unified.to_csv(full_qc_out, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 75)
    print("澳洲 AEMO 五大調度區 (2021-01) 統一寬表輸出完成")
    print("=" * 75)
    print(f"• 標準統一檔：{clean_out} ({len(clean_unified)} 筆, 唯一 PK: timestamp_utc)")
    print(f"• 完整稽核檔：{full_qc_out}")
    print("-" * 75)
    print(pd.DataFrame(summaries).to_string(index=False))
    print("=" * 75)


if __name__ == "__main__":
    run_unified_australia_202101()