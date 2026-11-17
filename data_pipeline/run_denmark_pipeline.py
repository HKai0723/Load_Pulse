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
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "Denmark_Energinet" / "DK_ConsumptionCategory_RAW_202101.csv"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

ZONES = ["DK1", "DK2"]
LOCAL_TZ = "Europe/Copenhagen"
START_UTC = "2021-01-01T00:00:00"
END_UTC = "2021-01-31T23:00:00"


def map_denmark_grid_zone(region_name: str) -> str:
    """依丹麥五大行政區映射至非同步電網分區 (DK1: 西丹麥大陸電網, DK2: 東丹麥北歐電網)。"""
    name = str(region_name).lower()
    if any(k in name for k in ("nordjylland", "midtjylland", "syddanmark")):
        return "DK1"
    if any(k in name for k in ("sjælland", "sjaelland", "hovedstaden")):
        return "DK2"
    raise ValueError(f"無法識別之丹麥行政區名稱：{region_name}")


def clean_single_zone(df_zone: pd.DataFrame, zone: str, utc_col: str) -> tuple[pd.DataFrame, dict]:
    """針對單一丹麥電網分區 (DK1 / DK2) 執行彙總、單位換算與品質檢核。"""
    cat_col = next((c for c in df_zone.columns if "category" in c.lower()), None)
    if cat_col:
        expected_combos = len(df_zone[["RegionName", cat_col]].drop_duplicates())
    else:
        expected_combos = 9 if zone == "DK1" else 6

    df_agg = (
        df_zone.groupby(utc_col, as_index=False)
        .agg(
            raw_timestamp=(utc_col, "first"),
            load_kwh=("ConsumptionkWh", lambda s: s.sum(min_count=expected_combos)),
        )
    )
    # 先由 kWh 除以 1,000 換算為 MWh，以符合 core_pipeline 支援的 energy_mwh 單位規範
    df_agg["load_mwh"] = df_agg["load_kwh"] / 1000.0
    df_agg["period_utc"] = pd.to_datetime(df_agg[utc_col], utc=True)

    df_norm = normalize_timestamp(
        df_agg,
        utc_col="period_utc",
        local_tz=LOCAL_TZ,
        raw_ts_col="raw_timestamp",
    )

    validate_frequency(df_norm, expected_freq="1h")
    df_dedup = detect_duplicates(df_norm)
    ts_map = df_dedup[["timestamp_utc", "raw_timestamp", "is_duplicate"]].drop_duplicates("timestamp_utc")

    df_hourly = resample_hourly(df_dedup, value_col="load_mwh", unit_type="energy_mwh")
    df_hourly = pd.merge(df_hourly, ts_map, on="timestamp_utc", how="left")

    df_complete = detect_missing_hours(
        df_hourly,
        start_utc=START_UTC,
        end_utc=END_UTC,
        local_tz=LOCAL_TZ,
    )
    df_complete["is_duplicate"] = df_complete["is_duplicate"].fillna(0).astype(int)

    df_validated = validate_load_values(df_complete, min_valid_mw=200.0, max_valid_mw=10000.0)
    df_flagged = generate_quality_flags(df_validated, is_source_revised=False)
    df_final = generate_calendar_features(df_flagged)

    summary = {
        "zone": zone,
        "raw_rows": len(df_zone),
        "hourly_rows": len(df_final),
        "missing": int(df_final["is_missing"].sum()),
        "outliers": int(df_final["is_suspected_outlier"].sum()),
        "min_mw": round(df_final["load_mw"].min(), 2),
        "mean_mw": round(df_final["load_mw"].mean(), 2),
        "max_mw": round(df_final["load_mw"].max(), 2),
    }
    return df_final, summary


def run_unified_denmark_202101():
    print(f"專案根目錄：{PROJECT_ROOT}\n")

    df_raw, _ = load_raw_data(
        file_path=RAW_FILE,
        source_name="Energinet_ConsumptionCategory_DK1_DK2",
    )

    utc_col = next((c for c in ["TimeUTC", "HourUTC"] if c in df_raw.columns), None)
    if utc_col is None or "RegionName" not in df_raw.columns or "ConsumptionkWh" not in df_raw.columns:
        raise KeyError(f"原始檔案缺少必要欄位，目前欄位：{df_raw.columns.tolist()}")

    df_raw["ConsumptionkWh"] = pd.to_numeric(df_raw["ConsumptionkWh"], errors="coerce")
    df_raw["grid_zone"] = df_raw["RegionName"].apply(map_denmark_grid_zone)

    zone_dfs: dict[str, pd.DataFrame] = {}
    summaries = []

    for zone in ZONES:
        print(f"\n{'=' * 55}")
        print(f"處理丹麥 Energinet 電網分區：{zone}")
        print(f"{'=' * 55}")
        df_sub = df_raw[df_raw["grid_zone"] == zone].copy()
        df_cleaned, stat = clean_single_zone(df_sub, zone, utc_col)
        zone_dfs[zone] = df_cleaned
        summaries.append(stat)

    # 以 DK1 建立唯一 UTC 主鍵與共用日曆基底表
    base_df = zone_dfs["DK1"][
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

    for zone in ZONES:
        df_z = zone_dfs[zone].copy()
        df_z["load_mw"] = df_z["load_mw"].round(3)

        sub_clean = df_z[["timestamp_utc", "load_mw", "quality_flag"]].rename(
            columns={
                "load_mw": f"{zone}_load_mw",
                "quality_flag": f"{zone}_quality_flag",
            }
        )
        clean_unified = pd.merge(
            clean_unified, sub_clean, on="timestamp_utc", how="outer", validate="one_to_one"
        )

        rename_map = {"raw_timestamp": f"{zone}_raw_timestamp", "load_mw": f"{zone}_load_mw"}
        for col in qc_flag_cols:
            rename_map[col] = f"{zone}_{col}"

        sub_qc = df_z[["timestamp_utc", "raw_timestamp", "load_mw"] + qc_flag_cols].rename(columns=rename_map)
        full_qc_unified = pd.merge(
            full_qc_unified, sub_qc, on="timestamp_utc", how="outer", validate="one_to_one"
        )

    clean_unified = clean_unified.sort_values("timestamp_utc").reset_index(drop=True)
    full_qc_unified = full_qc_unified.sort_values("timestamp_utc").reset_index(drop=True)
    assert clean_unified["timestamp_utc"].is_unique, "主鍵驗證失敗：timestamp_utc 存在重複值"

    for df_out in (clean_unified, full_qc_unified):
        df_out["timestamp_utc"] = df_out["timestamp_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        df_out["timestamp_local"] = df_out["timestamp_local"].apply(lambda ts: ts.isoformat())

    full_qc_unified["source_name"] = "Energinet_ConsumptionCategory_DK1_DK2"
    full_qc_unified["pipeline_version"] = PIPELINE_VERSION

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    clean_out = PROCESSED_DIR / "DK_Energinet_hourly_202101.csv"
    full_qc_out = PROCESSED_DIR / "DK_Energinet_hourly_202101_full_qc.csv"

    clean_unified.to_csv(clean_out, index=False, encoding="utf-8-sig")
    full_qc_unified.to_csv(full_qc_out, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 75)
    print("丹麥 Energinet (DK1 / DK2) 統一寬表輸出完成")
    print("=" * 75)
    print(f"• 標準統一檔：{clean_out} ({len(clean_unified)} 筆, 唯一 PK: timestamp_utc)")
    print(f"• 完整稽核檔：{full_qc_out}")
    print("-" * 75)
    print(pd.DataFrame(summaries).to_string(index=False))
    print("=" * 75)


if __name__ == "__main__":
    run_unified_denmark_202101()