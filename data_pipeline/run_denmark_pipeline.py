import pandas as pd
from pathlib import Path
from core_pipeline import (
    load_raw_data,
    normalize_timestamp,
    validate_frequency,
    detect_missing_hours,
    detect_duplicates,
    validate_load_values,
    generate_quality_flags,
    resample_hourly,
    generate_calendar_features,
    export_clean_dataset,
)

# ================= 動態定位專案根目錄 (Load_Pulse) =================
PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_FILE = PROJECT_ROOT / "data" / "raw" / "Denmark_Energinet" / "DK_ConsumptionCategory_RAW_202101.csv"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

PILOT_OUT = PROCESSED_DIR / "pilot_load_hourly.csv"
FULL_QC_OUT = PROCESSED_DIR / "DK_load_hourly_202101_full_qc.csv"

LOCAL_TZ = "Europe/Copenhagen"
START_UTC = "2021-01-01T00:00:00"
END_UTC = "2021-01-31T23:00:00"
# ===================================================================


def run_denmark_202101():
    print(f"📂 專案根目錄自動定位為：{PROJECT_ROOT}")
    print("🚀 開始執行丹麥 Energinet (2021-01) 標準化資料清洗管線...\n")

    # 1. 讀取原始檔
    df_raw, lineage = load_raw_data(
        file_path=RAW_FILE,
        source_name="Energinet_ConsumptionConsumerCategoryHour",
    )
    print(f"   原始欄位清單：{df_raw.columns.tolist()}")

    # 自動偵測時間與電量欄位名稱（相容新版 TimeUTC 與舊版 HourUTC）
    utc_col = next((c for c in ["TimeUTC", "HourUTC"] if c in df_raw.columns), None)
    dk_col = next((c for c in ["TimeDK", "HourDK"] if c in df_raw.columns), utc_col)
    val_col = next((c for c in ["ConsumptionkWh", "TotalCon"] if c in df_raw.columns), None)

    if not utc_col or not val_col:
        raise KeyError(f"找不到預期時間或電量欄位，目前欄位有：{df_raw.columns.tolist()}")

    # 丹麥前處理轉接：將各大區與三大部門之每小時 kWh 彙總為全丹麥逐時總用電量，並換算為 MW
    df_agg = (
        df_raw.groupby(utc_col, as_index=False)
        .agg(
            raw_timestamp=(utc_col, "first"),
            raw_hour_dk=(dk_col, "first"),
            total_kwh=(val_col, lambda s: s.sum(min_count=1)),
        )
    )
    df_agg["load_mw"] = df_agg["total_kwh"] / 1000.0

    # 2. 統一時區與時間欄位
    df_norm = normalize_timestamp(
        df_agg,
        utc_col=utc_col,
        local_tz=LOCAL_TZ,
        raw_ts_col="raw_timestamp",
    )

    # 3. 檢查取樣間隔
    validate_frequency(df_norm, expected_freq="1h")

    # 5. 偵測重複時間戳記
    df_dedup = detect_duplicates(df_norm)
    ts_map = df_dedup[["timestamp_utc", "raw_timestamp", "is_duplicate"]].drop_duplicates("timestamp_utc")

    # 8. 確保時間對齊標準逐小時
    df_hourly = resample_hourly(df_dedup, value_col="load_mw", unit_type="power_mw")
    df_hourly = pd.merge(df_hourly, ts_map, on="timestamp_utc", how="left")

    # 4. 偵測時間缺口（補齊 2021-01 全部 744 個 UTC 小時）
    df_complete = detect_missing_hours(
        df_hourly,
        start_utc=START_UTC,
        end_utc=END_UTC,
        local_tz=LOCAL_TZ,
    )
    df_complete["is_duplicate"] = df_complete["is_duplicate"].fillna(0).astype(int)

    # 6. 檢查數值範圍與可疑極端值
    df_validated = validate_load_values(df_complete, min_valid_mw=1000.0, max_valid_mw=10000.0)

    # 7. 產生品質旗標
    df_flagged = generate_quality_flags(df_validated, is_source_revised=False)

    # 9. 產生日期、星期、時段欄位
    df_final = generate_calendar_features(df_flagged)

    # 10. 輸出清洗結果
    export_clean_dataset(
        df=df_final,
        lineage=lineage,
        pilot_output_path=PILOT_OUT,
        full_qc_output_path=FULL_QC_OUT,
    )

    # ================= 印出品質報告摘要數據 =================
    print("\n" + "=" * 55)
    print("📋 丹麥 2021-01 清洗品質摘要（可直接填入 data_quality_report.md）")
    print("=" * 55)
    print(f"• 原始明細總筆數：{lineage['raw_row_count']:,} 筆（含全丹麥行政區與用戶分類）")
    print(f"• 聚合後逐時筆數：{len(df_final)} 筆（2021-01 共 31 天 × 24 小時）")
    print(f"• 缺失小時數 (is_missing)：{int(df_final['is_missing'].sum())} 筆 (缺失率 {df_final['is_missing'].mean()*100:.2f}%)")
    print(f"• 重複時間戳記 (is_duplicate)：{int(df_final['is_duplicate'].sum())} 筆")
    print(f"• DST 切換時數 (is_dst_transition)：{int(df_final['is_dst_transition'].sum())} 筆")
    print(f"• 可疑極端值 (is_suspected_outlier)：{int(df_final['is_suspected_outlier'].sum())} 筆")
    print(f"• 負載統計 (MW)：最小值 {df_final['load_mw'].min():.2f} | 平均 {df_final['load_mw'].mean():.2f} | 最大值 {df_final['load_mw'].max():.2f}")
    print("=" * 55)

    print("\n📊 pilot_load_hourly.csv 前 5 筆預覽：")
    preview_cols = ["timestamp_utc", "timestamp_local", "load_mw", "hour", "day_of_week", "is_weekend", "quality_flag"]
    print(df_final[preview_cols].head(5).to_string(index=False))


if __name__ == "__main__":
    run_denmark_202101()