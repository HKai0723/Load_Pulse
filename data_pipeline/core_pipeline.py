import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

PIPELINE_VERSION = "1.0.0"


# ==========================================
# [P1] 1. 讀取原始檔案
# ==========================================
def load_raw_data(file_path: Path, source_name: str) -> tuple[pd.DataFrame, dict]:
    """讀取原始 CSV，絕不覆寫原檔，並建立可追溯中繼資料 (Lineage)。"""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"找不到原始檔案：{file_path}")

    df = pd.read_csv(file_path)
    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc).isoformat()

    lineage = {
        "source_name": source_name,
        "raw_file": str(file_path.name),
        "downloaded_at_utc": file_mtime,
        "pipeline_version": PIPELINE_VERSION,
        "raw_row_count": len(df),
    }
    print(f"[1/10] load_raw_data(): 成功讀取 {len(df):,} 筆原始資料 ({file_path.name})")
    return df, lineage


# ==========================================
# [P1] 2. 統一時區與時間欄位
# ==========================================
def normalize_timestamp(
    df: pd.DataFrame,
    utc_col: str,
    local_tz: str,
    raw_ts_col: str | None = None,
) -> pd.DataFrame:
    """建立唯一 UTC 時間軸，並保留原始時間戳記、當地時間與 IANA 時區。"""
    df = df.copy()
    raw_col = raw_ts_col if raw_ts_col and raw_ts_col in df.columns else utc_col
    df["raw_timestamp"] = df[raw_col].astype(str)

    # 轉為標準 UTC 時區感知時間戳記
    df["timestamp_utc"] = pd.to_datetime(df[utc_col], utc=True)
    # 轉換為當地時區（保留 DST 偏移資訊，不可直接去重）
    df["timestamp_local"] = df["timestamp_utc"].dt.tz_convert(local_tz)
    df["iana_tz"] = local_tz

    df = df.sort_values("timestamp_utc").reset_index(drop=True)
    print(f"[2/10] normalize_timestamp(): 已建立 UTC 時間軸並對齊 IANA 時區 [{local_tz}]")
    return df


# ==========================================
# [P1] 3. 檢查取樣間隔
# ==========================================
def validate_frequency(df: pd.DataFrame, expected_freq: str = "1h") -> dict:
    """檢查相鄰時間戳記的取樣間隔是否符合預期。"""
    diffs = df["timestamp_utc"].diff().dropna()
    expected_td = pd.Timedelta(expected_freq)
    irregular_count = int((diffs != expected_td).sum())
    detected_mode = diffs.mode().iloc[0] if not diffs.empty else expected_td

    freq_report = {
        "expected_frequency": expected_freq,
        "detected_mode_interval": str(detected_mode),
        "irregular_interval_count": irregular_count,
    }
    print(
        f"[3/10] validate_frequency(): 預期間隔 {expected_freq}，"
        f"偵測眾數 {detected_mode}，異常間隔數 = {irregular_count}"
    )
    return freq_report


# ==========================================
# [P1] 4. 偵測時間缺口
# ==========================================
def detect_missing_hours(
    df: pd.DataFrame,
    start_utc: str,
    end_utc: str,
    local_tz: str,
) -> pd.DataFrame:
    """建立完整連續的 UTC 小時網格，補出缺失時間點並標記 is_missing（缺失值保持 NaN，絕不填 0）。"""
    df = df.copy()
    full_grid = pd.date_range(start=start_utc, end=end_utc, freq="1h", tz="UTC")
    grid_df = pd.DataFrame({"timestamp_utc": full_grid})

    merged = pd.merge(grid_df, df, on="timestamp_utc", how="left")
    merged["timestamp_local"] = merged["timestamp_utc"].dt.tz_convert(local_tz)
    merged["iana_tz"] = local_tz

    # 若該時間點原本不存在，或 load_mw 為 NaN，標記為缺失
    merged["is_missing"] = merged["load_mw"].isna().astype(int)
    missing_cnt = int(merged["is_missing"].sum())
    print(f"[4/10] detect_missing_hours(): 完整應有 {len(merged)} 小時，缺失時數 = {missing_cnt}")
    return merged


# ==========================================
# [P1] 5. 偵測重複時間戳記
# ==========================================
def detect_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """以 UTC 時間軸偵測重複時間戳記並加旗標（絕不直接用當地時間去重）。"""
    df = df.copy()
    df["is_duplicate"] = df.duplicated(subset=["timestamp_utc"], keep="first").astype(int)
    dup_cnt = int(df["is_duplicate"].sum())
    print(f"[5/10] detect_duplicates(): UTC 重複時間戳記筆數 = {dup_cnt}")
    return df


# ==========================================
# [P1] 6. 檢查單位、數值範圍與可疑值
# ==========================================
def validate_load_values(
    df: pd.DataFrame,
    min_valid_mw: float = 0.0,
    max_valid_mw: float = 20000.0,
) -> pd.DataFrame:
    """檢查負載數值範圍與 IQR 離群值，僅作標記，絕不刪除或平滑極端值。"""
    df = df.copy()
    valid_series = df["load_mw"].dropna()

    if len(valid_series) >= 4:
        q1 = valid_series.quantile(0.25)
        q3 = valid_series.quantile(0.75)
        iqr = q3 - q1
        lower_bound = max(min_valid_mw, q1 - 1.5 * iqr)
        upper_bound = min(max_valid_mw, q3 + 1.5 * iqr)
    else:
        lower_bound, upper_bound = min_valid_mw, max_valid_mw

    is_out_of_bounds = (df["load_mw"] <= min_valid_mw) | (df["load_mw"] > max_valid_mw)
    is_stat_outlier = (df["load_mw"] < lower_bound) | (df["load_mw"] > upper_bound)

    df["is_suspected_outlier"] = (is_out_of_bounds | is_stat_outlier).fillna(False).astype(int)
    outlier_cnt = int(df["is_suspected_outlier"].sum())
    print(
        f"[6/10] validate_load_values(): 正常統計區間 [{lower_bound:.1f}, {upper_bound:.1f}] MW，"
        f"可疑極端值 = {outlier_cnt} 筆"
    )
    return df


# ==========================================
# [P1] 7. 產生品質旗標
# ==========================================
def generate_quality_flags(df: pd.DataFrame, is_source_revised: bool = False) -> pd.DataFrame:
    """產生完整品質旗標欄位與整合摘要旗標 quality_flag。"""
    df = df.copy()

    # 偵測 DST 切換時刻（當地時區 UTC 偏移量發生變化的小時）
    offsets = df["timestamp_local"].apply(lambda ts: ts.utcoffset().total_seconds())
    dst_shift = (offsets != offsets.shift(1)) & (offsets.shift(1).notna())
    df["is_dst_transition"] = dst_shift.astype(int)

    # 預設不進行人工插補，忠實保留 NaN 並記錄為 0
    if "is_imputed" not in df.columns:
        df["is_imputed"] = 0

    df["is_source_revised"] = int(is_source_revised)

    # 組合可讀的綜合品質旗標（全正常則為 "OK"，異常則列出觸發項目）
    flag_cols = [
        ("MISSING", "is_missing"),
        ("DUPLICATE", "is_duplicate"),
        ("DST_TRANSITION", "is_dst_transition"),
        ("IMPUTED", "is_imputed"),
        ("OUTLIER", "is_suspected_outlier"),
        ("REVISED", "is_source_revised"),
    ]

    def _summarize_flags(row):
        active = [label for label, col in flag_cols if row.get(col, 0) == 1]
        return "OK" if not active else "|".join(active)

    df["quality_flag"] = df.apply(_summarize_flags, axis=1)
    print(f"[7/10] generate_quality_flags(): 已產生 6 項明細旗標與綜合 quality_flag")
    return df


# ==========================================
# [P2] 8. 必要時轉為逐小時
# ==========================================
def resample_hourly(df: pd.DataFrame, value_col: str, unit_type: str = "power_mw") -> pd.DataFrame:
    """
    依物理單位正確聚合為逐小時平均功率 (MW)：
    - power_mw: 功率取平均 (.mean())
    - energy_mwh: 電能取加總 (.sum(min_count=1))
    """
    df = df.copy().set_index("timestamp_utc")
    if unit_type == "power_mw":
        hourly = df[[value_col]].resample("1h").mean()
    elif unit_type == "energy_mwh":
        hourly = df[[value_col]].resample("1h").sum(min_count=1)
    else:
        raise ValueError("unit_type 必須為 'power_mw' 或 'energy_mwh'")

    hourly = hourly.rename(columns={value_col: "load_mw"}).reset_index()
    print(f"[8/10] resample_hourly(): 已依 [{unit_type}] 規範完成 1 小時聚合")
    return hourly


# ==========================================
# [P2] 9. 產生日期、星期、時段欄位
# ==========================================
def generate_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """依據當地作息時間 (timestamp_local) 產生 hour, day_of_week, is_weekend。"""
    df = df.copy()
    df["hour"] = df["timestamp_local"].dt.hour
    df["day_of_week"] = df["timestamp_local"].dt.dayofweek + 1  # 1=週一, 7=週日 (ISO-8601)
    df["is_weekend"] = df["day_of_week"].isin([6, 7]).astype(int)
    print("[9/10] generate_calendar_features(): 已產生 hour, day_of_week (1-7), is_weekend 欄位")
    return df


# ==========================================
# [P1] 10. 輸出清洗結果
# ==========================================
def export_clean_dataset(
    df: pd.DataFrame,
    lineage: dict,
    pilot_output_path: Path,
    full_qc_output_path: Path,
) -> None:
    """輸出符合工作單第 4 節規範的 pilot_load_hourly.csv 與完整溯源品質檢核表。"""
    df_out = df.copy()
    df_out["load_mw"] = df_out["load_mw"].round(3)

    # 格式化時間字串：UTC 採標準 Z 格式，Local 保留時區偏移防 DST 歧義
    df_out["timestamp_utc"] = df_out["timestamp_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    df_out["timestamp_local"] = df_out["timestamp_local"].apply(lambda ts: ts.isoformat())

    # 附上溯源欄位至完整版
    for k, v in lineage.items():
        df_out[k] = v

    # 輸出 A：工作單第 4 節標準 7 欄位 Pilot 檔
    pilot_cols = [
        "timestamp_utc",
        "timestamp_local",
        "load_mw",
        "hour",
        "day_of_week",
        "is_weekend",
        "quality_flag",
    ]
    pilot_output_path.parent.mkdir(parents=True, exist_ok=True)
    df_out[pilot_cols].to_csv(pilot_output_path, index=False, encoding="utf-8-sig")

    # 輸出 B：完整品質旗標與溯源版（供撰寫 data_quality_report.md 與稽核用）
    full_cols = [
        "timestamp_utc",
        "timestamp_local",
        "iana_tz",
        "raw_timestamp",
        "load_mw",
        "hour",
        "day_of_week",
        "is_weekend",
        "is_missing",
        "is_duplicate",
        "is_dst_transition",
        "is_imputed",
        "is_suspected_outlier",
        "is_source_revised",
        "quality_flag",
        "source_name",
        "raw_file",
        "downloaded_at_utc",
        "pipeline_version",
    ]
    available_full_cols = [c for c in full_cols if c in df_out.columns]
    df_out[available_full_cols].to_csv(full_qc_output_path, index=False, encoding="utf-8-sig")

    print(f"[10/10] export_clean_dataset():")
    print(f"   -> 標準 Pilot 檔已輸出：{pilot_output_path.resolve()} ({len(df_out)} 筆)")
    print(f"   -> 完整品質溯源檔已輸出：{full_qc_output_path.resolve()}")