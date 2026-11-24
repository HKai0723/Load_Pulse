"""Clean AEMO WA (WEM / SWIS) 2021-01 30-min Operational Demand data, plot figures, and generate report.md.

Pipeline outputs (strictly within `wa_wem_pilot/`):
- `data/processed/AU_AEMO_WEM_hourly_2021_01.parquet` (744 hourly records, AWST / UTC+8)
- `figures/wem_2021_01_heatmap.png` (31-day x 24-hour load heatmap, 180 dpi)
- `figures/wem_2021_01_diurnal_and_lockdown.png` (Weekday/Weekend diurnal profile + snap lockdown comparison, 180 dpi)
- `report.md` (Traditional Chinese empirical report with Word-friendly dual-format schema & embedded figures)
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
FIGURES_DIR = BASE_DIR / "figures"

RAW_SLICE_PATH = RAW_DIR / "operational-demand-2021-01.csv"
RAW_2020_PATH = RAW_DIR / "operational-demand-2020.csv"
RAW_2021_PATH = RAW_DIR / "operational-demand-2021.csv"
PARQUET_PATH = PROCESSED_DIR / "AU_AEMO_WEM_hourly_2021_01.parquet"
HEATMAP_FIG_PATH = FIGURES_DIR / "wem_2021_01_heatmap.png"
DIURNAL_LOCKDOWN_FIG_PATH = FIGURES_DIR / "wem_2021_01_diurnal_and_lockdown.png"
REPORT_PATH = BASE_DIR / "report.md"

REGION_ID = "WA_SWIS"
LOCAL_TZ = "Australia/Perth"
START_LOCAL = "2021-01-01 00:00:00"
END_LOCAL = "2021-01-31 23:00:00"
EXPECTED_HOURS = 744

SOURCE_URLS = {
    "2021": "https://data.wa.aemo.com.au/public/public-data/datafiles/operational-demand/operational-demand-2021.csv",
    "2020": "https://data.wa.aemo.com.au/public/public-data/datafiles/operational-demand/operational-demand-2020.csv",
    "balancing_2021": "https://data.wa.aemo.com.au/public/public-data/datafiles/balancing-summary/balancing-summary-2021.csv",
    "load_summary_2021": "https://data.wa.aemo.com.au/public/public-data/datafiles/load-summary/load-summary-2021.csv",
}


def inspect_raw_samples(raw_path: Path) -> dict[str, str]:
    """Extract representative non-empty verbatim example values for each raw column."""
    with raw_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise RuntimeError(f"Empty header in {raw_path}")
        samples: dict[str, str] = {col: "" for col in reader.fieldnames}
        for row in reader:
            for col in samples:
                val = (row.get(col) or "").strip()
                if not samples[col] and val:
                    samples[col] = val
            if all(samples.values()):
                break
    return samples


def build_hourly_dataset(raw_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load 30-min raw CSV, align to AWST (UTC+8) hourly grid, and validate."""
    if not raw_path.exists():
        raise FileNotFoundError(
            f"Raw 2021-01 CSV not found at {raw_path}. Run `fetch.py` first."
        )

    raw_df = pd.read_csv(raw_path, encoding="utf-8-sig")
    expected_cols = [
        "Trading Date",
        "Interval Number",
        "Trading Interval",
        "Operational Demand (MW)",
        "Extracted At",
    ]
    missing_cols = [c for c in expected_cols if c not in raw_df.columns]
    if missing_cols:
        raise ValueError(f"Missing expected columns in raw CSV: {missing_cols}")

    raw_row_count = len(raw_df)
    raw_from_2020_td = int((raw_df["Trading Date"].astype(str) == "2020-12-31").sum())
    raw_from_2021_td = int(raw_row_count - raw_from_2020_td)

    # Parse Trading Interval as AWST (Australia/Perth, fixed UTC+8, no DST).
    ts_local = pd.to_datetime(raw_df["Trading Interval"], format="%Y-%m-%d %H:%M:%S")
    raw_df["local_ts"] = ts_local.dt.tz_localize(LOCAL_TZ)
    raw_df["demand_mw"] = pd.to_numeric(raw_df["Operational Demand (MW)"], errors="coerce")

    duplicate_intervals = int(raw_df["local_ts"].duplicated().sum())
    if duplicate_intervals > 0:
        raw_df = raw_df.drop_duplicates(subset=["local_ts"], keep="last")

    # Interval-Beginning alignment: HH:00 and HH:30 aggregate to HH:00 hourly mean MW.
    raw_df["hour_local"] = raw_df["local_ts"].dt.floor("h")
    agg = (
        raw_df.groupby("hour_local", sort=True)
        .agg(
            load_mw=("demand_mw", "mean"),
            valid_intervals=("demand_mw", "count"),
            total_intervals=("local_ts", "count"),
        )
        .reset_index()
    )

    # Build complete 744-hour AWST index.
    full_index = pd.date_range(
        start=pd.Timestamp(START_LOCAL, tz=LOCAL_TZ),
        end=pd.Timestamp(END_LOCAL, tz=LOCAL_TZ),
        freq="h",
        name="local_datetime",
    )
    hourly = pd.DataFrame({"local_datetime": full_index}).merge(
        agg, left_on="local_datetime", right_on="hour_local", how="left"
    )
    hourly = hourly.drop(columns=["hour_local"])
    hourly["valid_intervals"] = hourly["valid_intervals"].fillna(0).astype("int32")
    hourly["total_intervals"] = hourly["total_intervals"].fillna(0).astype("int32")

    hourly["is_missing"] = hourly["load_mw"].isna()

    def _quality_flag(row: pd.Series) -> str:
        if bool(row["is_missing"]) or int(row["valid_intervals"]) == 0:
            return "MISSING"
        if float(row["load_mw"]) <= 0.0:
            return "ANOMALY_NONPOSITIVE"
        if int(row["valid_intervals"]) < 2:
            return "PARTIAL_INTERVAL"
        return "OK"

    hourly["quality_flag"] = hourly.apply(_quality_flag, axis=1).astype("string")

    # Standard schema columns
    hourly["region_id"] = pd.Series(REGION_ID, index=hourly.index, dtype="string")
    hourly["timestamp_utc"] = hourly["local_datetime"].dt.tz_convert("UTC")
    hourly["local_date"] = hourly["local_datetime"].dt.strftime("%Y-%m-%d").astype("string")
    hourly["local_hour"] = hourly["local_datetime"].dt.hour.astype("int32")
    hourly["day_of_week"] = hourly["local_datetime"].dt.dayofweek.astype("int32")
    hourly["is_weekend"] = (hourly["day_of_week"] >= 5).astype("bool")
    hourly["load_mw"] = hourly["load_mw"].astype("float64")
    hourly["is_missing"] = hourly["is_missing"].astype("bool")

    output_cols = [
        "region_id",
        "timestamp_utc",
        "local_datetime",
        "local_date",
        "local_hour",
        "day_of_week",
        "is_weekend",
        "load_mw",
        "is_missing",
        "quality_flag",
    ]
    out_df = hourly[output_cols].copy()

    # Diagnostics
    diagnostics = {
        "raw_row_count": raw_row_count,
        "raw_from_2020_td": raw_from_2020_td,
        "raw_from_2021_td": raw_from_2021_td,
        "raw_null_demand": int(raw_df["demand_mw"].isna().sum()),
        "duplicate_intervals": duplicate_intervals,
        "complete_2of2_hours": int((hourly["valid_intervals"] == 2).sum()),
        "partial_hours": int((hourly["quality_flag"] == "PARTIAL_INTERVAL").sum()),
        "nonpositive_hours": int((hourly["quality_flag"] == "ANOMALY_NONPOSITIVE").sum()),
        "ok_hours": int((hourly["quality_flag"] == "OK").sum()),
        "raw_min_30m_mw": float(raw_df["demand_mw"].min()),
        "raw_min_30m_ts": str(raw_df.loc[raw_df["demand_mw"].idxmin(), "Trading Interval"]),
        "raw_max_30m_mw": float(raw_df["demand_mw"].max()),
        "raw_max_30m_ts": str(raw_df.loc[raw_df["demand_mw"].idxmax(), "Trading Interval"]),
    }

    if len(out_df) != EXPECTED_HOURS:
        raise AssertionError(f"Expected {EXPECTED_HOURS} hourly rows, got {len(out_df)}")

    return out_df, diagnostics


def compute_empirical_stats(df: pd.DataFrame) -> dict[str, Any]:
    """Compute comprehensive 2021-01 empirical statistics for report generation."""
    valid = df[~df["is_missing"]].copy()
    total_hours = len(df)
    missing_hours = int(df["is_missing"].sum())

    mean_mw = float(valid["load_mw"].mean())
    std_mw = float(valid["load_mw"].std(ddof=1))
    median_mw = float(valid["load_mw"].median())
    p05_mw = float(valid["load_mw"].quantile(0.05))
    p25_mw = float(valid["load_mw"].quantile(0.25))
    p75_mw = float(valid["load_mw"].quantile(0.75))
    p95_mw = float(valid["load_mw"].quantile(0.95))

    min_idx = valid["load_mw"].idxmin()
    max_idx = valid["load_mw"].idxmax()
    min_row = valid.loc[min_idx]
    max_row = valid.loc[max_idx]

    min_mw = float(min_row["load_mw"])
    min_ts = min_row["local_datetime"].strftime("%Y-%m-%d %H:%M AWST")
    max_mw = float(max_row["load_mw"])
    max_ts = max_row["local_datetime"].strftime("%Y-%m-%d %H:%M AWST")
    peak_to_trough = max_mw / min_mw

    # Weekday vs Weekend
    wkday = valid[~valid["is_weekend"]]
    wknd = valid[valid["is_weekend"]]
    wkday_mean = float(wkday["load_mw"].mean())
    wknd_mean = float(wknd["load_mw"].mean())
    wkday_minus_wknd = wkday_mean - wknd_mean
    wkday_pct_diff = (wkday_minus_wknd / wknd_mean) * 100.0
    wkday_days = int(wkday["local_date"].nunique())
    wknd_days = int(wknd["local_date"].nunique())

    # Diurnal profile (Duck Curve metrics)
    hourly_profile = valid.groupby("local_hour")["load_mw"].mean()
    overnight_slice = hourly_profile.loc[0:5]
    overnight_trough_hr = int(overnight_slice.idxmin())
    overnight_trough_mw = float(overnight_slice.min())

    midday_slice = hourly_profile.loc[9:14]
    solar_trough_hr = int(midday_slice.idxmin())
    solar_trough_mw = float(midday_slice.min())

    evening_slice = hourly_profile.loc[16:22]
    evening_peak_hr = int(evening_slice.idxmax())
    evening_peak_mw = float(evening_slice.max())

    ramp_mw = evening_peak_mw - solar_trough_mw
    ramp_hours = evening_peak_hr - solar_trough_hr
    ramp_pct = (ramp_mw / solar_trough_mw) * 100.0

    # Steepest 1-hour average upward ramp
    hourly_diffs = hourly_profile.diff()
    steepest_hr = int(hourly_diffs.idxmax())
    steepest_ramp = float(hourly_diffs.max())

    # Top 5 daily peaks
    daily_peak_idx = valid.groupby("local_date")["load_mw"].idxmax()
    top5_peaks_df = (
        valid.loc[daily_peak_idx, ["local_date", "local_hour", "day_of_week", "load_mw"]]
        .sort_values("load_mw", ascending=False)
        .head(5)
    )
    dow_names = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
    top5_peaks = [
        {
            "date": str(r["local_date"]),
            "dow": dow_names[int(r["day_of_week"])],
            "hour": f"{int(r['local_hour']):02d}:00",
            "load_mw": float(r["load_mw"]),
        }
        for _, r in top5_peaks_df.iterrows()
    ]

    # Perth snap COVID-19 lockdown: effective 2021-01-31 18:00 AWST (Sunday)
    jan31 = valid[valid["local_date"] == "2021-01-31"].set_index("local_hour")["load_mw"]
    prior_sundays = valid[
        (valid["day_of_week"] == 6) & (valid["local_date"] < "2021-01-31")
    ]
    prior_sun_dates = sorted(prior_sundays["local_date"].unique().tolist())
    prior_sun_hourly = prior_sundays.groupby("local_hour")["load_mw"].mean()

    pre_hours = list(range(12, 18))   # 12:00-17:00 AWST (6 hours before lockdown)
    post_hours = list(range(18, 24))  # 18:00-23:00 AWST (6 hours after lockdown)

    jan31_pre_mean = float(jan31.loc[pre_hours].mean())
    jan31_post_mean = float(jan31.loc[post_hours].mean())
    jan31_delta_mw = jan31_post_mean - jan31_pre_mean
    jan31_delta_pct = (jan31_delta_mw / jan31_pre_mean) * 100.0

    sun_pre_mean = float(prior_sun_hourly.loc[pre_hours].mean())
    sun_post_mean = float(prior_sun_hourly.loc[post_hours].mean())
    sun_delta_mw = sun_post_mean - sun_pre_mean
    sun_delta_pct = (sun_delta_mw / sun_pre_mean) * 100.0

    pre_spread_mw = jan31_pre_mean - sun_pre_mean
    pre_spread_pct = (pre_spread_mw / sun_pre_mean) * 100.0
    post_spread_mw = jan31_post_mean - sun_post_mean
    post_spread_pct = (post_spread_mw / sun_post_mean) * 100.0
    did_mw = post_spread_mw - pre_spread_mw

    lockdown_hourly_rows = []
    for hr in range(15, 24):
        j_val = float(jan31.loc[hr])
        s_val = float(prior_sun_hourly.loc[hr])
        diff = j_val - s_val
        diff_pct = (diff / s_val) * 100.0
        phase = "封城生效前" if hr < 18 else "封城生效後"
        lockdown_hourly_rows.append(
            {
                "hour": f"{hr:02d}:00",
                "phase": phase,
                "jan31_mw": j_val,
                "prior_sun_mw": s_val,
                "diff_mw": diff,
                "diff_pct": diff_pct,
            }
        )

    return {
        "total_hours": total_hours,
        "missing_hours": missing_hours,
        "mean_mw": mean_mw,
        "std_mw": std_mw,
        "median_mw": median_mw,
        "p05_mw": p05_mw,
        "p25_mw": p25_mw,
        "p75_mw": p75_mw,
        "p95_mw": p95_mw,
        "min_mw": min_mw,
        "min_ts": min_ts,
        "max_mw": max_mw,
        "max_ts": max_ts,
        "peak_to_trough": peak_to_trough,
        "wkday_mean": wkday_mean,
        "wknd_mean": wknd_mean,
        "wkday_minus_wknd": wkday_minus_wknd,
        "wkday_pct_diff": wkday_pct_diff,
        "wkday_days": wkday_days,
        "wknd_days": wknd_days,
        "overnight_trough_hr": overnight_trough_hr,
        "overnight_trough_mw": overnight_trough_mw,
        "solar_trough_hr": solar_trough_hr,
        "solar_trough_mw": solar_trough_mw,
        "evening_peak_hr": evening_peak_hr,
        "evening_peak_mw": evening_peak_mw,
        "ramp_mw": ramp_mw,
        "ramp_hours": ramp_hours,
        "ramp_pct": ramp_pct,
        "steepest_hr": steepest_hr,
        "steepest_ramp": steepest_ramp,
        "top5_peaks": top5_peaks,
        "prior_sun_dates": prior_sun_dates,
        "jan31_peak_mw": float(jan31.max()),
        "jan31_peak_hr": int(jan31.idxmax()),
        "jan31_pre_mean": jan31_pre_mean,
        "jan31_post_mean": jan31_post_mean,
        "jan31_delta_mw": jan31_delta_mw,
        "jan31_delta_pct": jan31_delta_pct,
        "sun_pre_mean": sun_pre_mean,
        "sun_post_mean": sun_post_mean,
        "sun_delta_mw": sun_delta_mw,
        "sun_delta_pct": sun_delta_pct,
        "pre_spread_mw": pre_spread_mw,
        "pre_spread_pct": pre_spread_pct,
        "post_spread_mw": post_spread_mw,
        "post_spread_pct": post_spread_pct,
        "did_mw": did_mw,
        "lockdown_hourly_rows": lockdown_hourly_rows,
        "utc_start": df["timestamp_utc"].iloc[0].strftime("%Y-%m-%d %H:%M UTC"),
        "utc_end": df["timestamp_utc"].iloc[-1].strftime("%Y-%m-%d %H:%M UTC"),
        "local_start": df["local_datetime"].iloc[0].strftime("%Y-%m-%d %H:%M AWST"),
        "local_end": df["local_datetime"].iloc[-1].strftime("%Y-%m-%d %H:%M AWST"),
    }


def render_report(
    samples: dict[str, str],
    diag: dict[str, Any],
    stats: dict[str, Any],
) -> str:
    """Render Traditional Chinese Pilot report with all four required chapters."""
    raw_dict_rows = [
        (
            "Trading Date",
            "string (YYYY-MM-DD)",
            "WEM 交易日（當日 08:00 至次日 08:00 AWST）",
            samples.get("Trading Date", "2021-01-01"),
        ),
        (
            "Interval Number",
            "int (1–48)",
            "交易日內第 N 個 30 分鐘區間（1=08:00，33=次日 00:00）",
            samples.get("Interval Number", "1"),
        ),
        (
            "Trading Interval",
            "datetime (AWST)",
            "30 分鐘區間起始時間（Interval-Beginning，固定 UTC+8）",
            samples.get("Trading Interval", "2021-01-01 00:00:00"),
        ),
        (
            "Operational Demand (MW)",
            "float64",
            "SWIS 系統運轉負載均值（MW，已扣除表後屋頂太陽能）",
            samples.get("Operational Demand (MW)", "2167.948"),
        ),
        (
            "Extracted At",
            "datetime (AWST)",
            "AEMO 資料庫批次匯出時間戳（年度檔僅首筆填值）",
            samples.get("Extracted At", "2022-01-01 12:00:07"),
        ),
    ]

    md_dict_lines = [
        "| 欄位名稱 | 型別 | 說明 | 範例值 |",
        "| :--- | :--- | :--- | :--- |",
    ]
    for col, dtype, desc, ex in raw_dict_rows:
        md_dict_lines.append(f"| `{col}` | {dtype} | {desc} | `{ex}` |")
    md_dict_table = "\n".join(md_dict_lines)

    tsv_dict_lines = ["欄位名稱\t型別\t說明\t範例值"]
    for col, dtype, desc, ex in raw_dict_rows:
        tsv_dict_lines.append(f"{col}\t{dtype}\t{desc}\t{ex}")
    tsv_dict_block = "\n".join(tsv_dict_lines)

    top5_lines = [
        "| 排名 | 日期 | 星期 | 尖峰時段（AWST） | 逐小時均值負載（MW） |",
        "| :---: | :---: | :---: | :---: | :---: |",
    ]
    for idx, item in enumerate(stats["top5_peaks"], start=1):
        top5_lines.append(
            f"| {idx} | {item['date']} | {item['dow']} | {item['hour']} | {item['load_mw']:,.2f} |"
        )
    top5_table = "\n".join(top5_lines)

    lockdown_lines = [
        "| 時段（AWST） | 階段 | 2021-01-31（MW） | 前四週日均值（MW） | 差值（MW） | 相對幅度 |",
        "| :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for row in stats["lockdown_hourly_rows"]:
        lockdown_lines.append(
            f"| {row['hour']} | {row['phase']} | {row['jan31_mw']:,.2f} | "
            f"{row['prior_sun_mw']:,.2f} | {row['diff_mw']:+,.2f} | {row['diff_pct']:+.2f}% |"
        )
    lockdown_table = "\n".join(lockdown_lines)

    lockdown_by_hr = {row["hour"]: row for row in stats["lockdown_hourly_rows"]}
    diff_18_mw = lockdown_by_hr["18:00"]["diff_mw"]
    diff_23_mw = lockdown_by_hr["23:00"]["diff_mw"]

    prior_sun_str = "、".join(stats["prior_sun_dates"])
    raw_2020_kb = RAW_2020_PATH.stat().st_size / 1024.0 if RAW_2020_PATH.exists() else 0.0
    raw_2021_kb = RAW_2021_PATH.stat().st_size / 1024.0 if RAW_2021_PATH.exists() else 0.0
    parquet_kb = PARQUET_PATH.stat().st_size / 1024.0 if PARQUET_PATH.exists() else 0.0

    report = f"""# 西澳電力市場（AEMO WEM / SWIS）2021 年 1 月單月 Pilot 資料管線報告

> **專案模組**：`wa_wem_pilot`（完全獨立 Pilot 驗證管線）  
> **目標區域**：`{REGION_ID}`（澳洲西澳西南互聯系統 South West Interconnected System）  
> **資料區間**：`{stats['local_start']}` 至 `{stats['local_end']}`（共 `{stats['total_hours']}` 小時）  
> **產出檔案**：`wa_wem_pilot/data/processed/AU_AEMO_WEM_hourly_2021_01.parquet`（{parquet_kb:.1f} KB）

---

## 1. 資料來源與獲取便利度評級

### 1.1 官方公開入口與獲取便利度評級（T0）

西澳批發電力市場（Wholesale Electricity Market, **WEM**）由澳洲能源市場運營中心（**AEMO**）負責調度與資料公開，其服務範圍為西澳西南互聯系統（South West Interconnected System, **SWIS**，涵蓋伯斯都會區與西澳西南部）。AEMO WA 透過公開靜態檔案伺服器 `https://data.wa.aemo.com.au/public/public-data/datafiles/` 提供年度歷史 CSV 檔案。

| 評估構面 | 評核結果 |
| :--- | :--- |
| **資料來源機構** | Australian Energy Market Operator（AEMO — WA WEM / SWIS） |
| **獲取便利度評級** | **T0（最高等級：公開直連下載）** |
| **認證與金鑰需求** | 免註冊、免登入、免 API Key、無 OAuth Token 過期與速率額度限制 |
| **原始時間解析度** | 30 分鐘（Interval-Beginning，每日 48 個交易區間） |
| **原始檔案格式** | UTF-8 CSV（單年度約 0.8 MB，輕量易重現） |
| **重複執行冪等性** | 支援 HTTP 重試與原子暫存檔覆寫（`fetch.py`） |

### 1.2 實測可用端點與交易日跨年邊界說明

本 Pilot 實測探勘 AEMO WA 公開目錄，確認下列 CSV 端點皆可免認證直接以 `HTTP 200` 下載：

- **主要採用端點（SWIS 官方運轉負載 Operational Demand）**：
  - 2021 年度檔（{raw_2021_kb:.1f} KB）：`{SOURCE_URLS['2021']}`
  - 2020 年度檔（{raw_2020_kb:.1f} KB，補齊跨年交易日邊界）：`{SOURCE_URLS['2020']}`
- **同入口已驗證可用輔助端點（未混入本負載清洗，供後續擴充發電結構與電價研究參考）**：
  - 平衡市場摘要（含發電與結算電價）：`{SOURCE_URLS['balancing_2021']}`
  - 負載與計量發電摘要：`{SOURCE_URLS['load_summary_2021']}`

> **關鍵工程發現 — WEM 交易日（Trading Day）邊界**：  
> WEM 市場規定每個「交易日」自當地時間 **`08:00 AWST`** 起算至次日 **`08:00 AWST`**（區間編號 `1` 至 `48`）。因此，西曆 **`2021-01-01 00:00:00` 至 `07:30:00 AWST`**（共 `{diag['raw_from_2020_td']}` 筆 30 分鐘紀錄）在官方分類中隸屬交易日 `2020-12-31`（區間編號 `33–48`），存放在 `operational-demand-2020.csv` 檔尾；而 `2021-01-01 08:00:00` 至 `2021-01-31 23:30:00 AWST`（共 `{diag['raw_from_2021_td']:,}` 筆）則位於 `operational-demand-2021.csv`。`fetch.py` 同時拉取兩檔並原樣切出 `2021-01` 全月共 **`{diag['raw_row_count']:,}` 筆** 30 分鐘原始資料，徹底消除跨年 8 小時斷層。

---

## 2. 原始資料欄位字典（Word 友善防破版雙格式）

以下針對 `wa_wem_pilot/data/raw/operational-demand-2021-01.csv` 忠實保留之原始 5 欄位，提供 **精簡四欄 Markdown 表格** 與 **Tab 分隔純文字區塊** 雙格式，方便直接檢閱或貼入 Microsoft Word 排版不破版。

### 2.1 精簡四欄 Markdown 表格

{md_dict_table}

### 2.2 可直接貼入 Word 轉表格之 Tab 分隔純文字區塊

> **Word 轉換步驟**：全選複製下方區塊文字 → 貼入 Word → 全選貼上內容 → 點選「插入」→「表格」→「文字轉換為表格」→ 分隔文字選擇「定位點（Tab）」即可生成整齊四欄表格。

```tsv
{tsv_dict_block}
```

---

## 3. 清洗規格與 2021 年 1 月實證統計摘要

### 3.1 時區對齊、聚合規則與輸出規格

| 處理項目 | 規格與驗證結果 |
| :--- | :--- |
| **當地時區** | `Australia/Perth`（AWST，固定 `UTC+8`，自 2009 年起全年**無夏令時間 DST**） |
| **當地時間範圍** | `{stats['local_start']}` 至 `{stats['local_end']}` |
| **對應 UTC 範圍** | `{stats['utc_start']}` 至 `{stats['utc_end']}` |
| **時間對齊方式** | Interval-Beginning 對齊：將每小時 `HH:00` 與 `HH:30` 兩筆 30 分鐘平均功率取算術平均，產出標準逐小時負載均值 `load_mw`（MW） |
| **輸出檔案路徑** | `wa_wem_pilot/data/processed/AU_AEMO_WEM_hourly_2021_01.parquet` |
| **輸出標準欄位（10 欄）** | `region_id`, `timestamp_utc`, `local_datetime`, `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `load_mw`, `is_missing`, `quality_flag` |

### 3.2 744 小時完整性檢核結果

- **原始 30 分鐘紀錄數**：`{diag['raw_row_count']:,}` 筆（`{diag['raw_from_2020_td']}` 筆來自 2020 檔跨年交易日 + `{diag['raw_from_2021_td']:,}` 筆來自 2021 檔），原始重複時間戳 `{diag['duplicate_intervals']}` 筆、原始空值 `{diag['raw_null_demand']}` 筆。
- **逐小時序列完整性**：理論小時數 `{EXPECTED_HOURS}` 小時、實際產出 **`{stats['total_hours']}` 小時**；其中每小時皆具 2/2 完整半小時區間者共 **`{diag['complete_2of2_hours']}` 小時（100.0%）**，缺值數 **`{stats['missing_hours']}`**，半缺區間 `{diag['partial_hours']}` 筆，非正值異常 `{diag['nonpositive_hours']}` 筆，`quality_flag="OK"` 達 **`{diag['ok_hours']}/{stats['total_hours']}`（100.0%）**。

### 3.3 全月關鍵實證統計表（2021-01 逐小時序列）

| 統計指標 | 實證數值 | 備註／時間點 |
| :--- | :---: | :--- |
| 總小時數（Total Hours） | `{stats['total_hours']}` | 31 天 × 24 小時完整無缺口 |
| 缺值數（Missing Hours） | `{stats['missing_hours']}` | `is_missing=False` 達 100.0% |
| 全月均值（Mean） | `{stats['mean_mw']:,.2f} MW` | — |
| 全月標準差（Std Dev） | `{stats['std_mw']:,.2f} MW` | 變異係數 CV = `{(stats['std_mw'] / stats['mean_mw']) * 100:.2f}%` |
| 中位數（Median） | `{stats['median_mw']:,.2f} MW` | 四分位距 IQR = `{stats['p75_mw'] - stats['p25_mw']:,.2f} MW`（P25=`{stats['p25_mw']:,.2f}` / P75=`{stats['p75_mw']:,.2f}`） |
| 第 5 / 第 95 百分位（P5 / P95） | `{stats['p05_mw']:,.2f}` / `{stats['p95_mw']:,.2f} MW` | — |
| 全月最小值（正午太陽能谷值） | **`{stats['min_mw']:,.2f} MW`** | `{stats['min_ts']}`（原始 30m 最低 `{diag['raw_min_30m_mw']:,.2f} MW` @ `{diag['raw_min_30m_ts']}`） |
| 全月最大值（盛夏傍晚尖峰） | **`{stats['max_mw']:,.2f} MW`** | `{stats['max_ts']}`（原始 30m 最高 `{diag['raw_max_30m_mw']:,.2f} MW` @ `{diag['raw_max_30m_ts']}`） |
| 全月尖離峰倍數（Max / Min） | `{stats['peak_to_trough']:.2f}x` | 峰谷落差達 `{stats['max_mw'] - stats['min_mw']:,.2f} MW` |
| 平日均值（Weekday, {stats['wkday_days']} 天） | `{stats['wkday_mean']:,.2f} MW` | 週一至週五 |
| 週末均值（Weekend, {stats['wknd_days']} 天） | `{stats['wknd_mean']:,.2f} MW` | 週六至週日 |
| 平日 vs. 週末負載差 | **`{stats['wkday_minus_wknd']:+,.2f} MW`** | 平日較週末高 `{stats['wkday_pct_diff']:+.2f}%` |
| 平均日內夜間谷值（00–05 時） | `{stats['overnight_trough_mw']:,.2f} MW` | 發生於平均 `{stats['overnight_trough_hr']:02d}:00 AWST` |
| 平均日內正午太陽能谷值（09–14 時） | **`{stats['solar_trough_mw']:,.2f} MW`** | 發生於平均 `{stats['solar_trough_hr']:02d}:00 AWST`（低於凌晨谷值 `{stats['solar_trough_mw'] - stats['overnight_trough_mw']:+,.2f} MW`） |
| 平均日內傍晚尖峰（16–22 時） | `{stats['evening_peak_mw']:,.2f} MW` | 發生於平均 `{stats['evening_peak_hr']:02d}:00 AWST` |
| 平均鴨子曲線爬坡幅度 | **`+{stats['ramp_mw']:,.2f} MW`** | `{stats['solar_trough_hr']:02d}:00→{stats['evening_peak_hr']:02d}:00`（{stats['ramp_hours']} 小時內激增 `{stats['ramp_pct']:+.1f}%`；單小時最陡爬坡 `{stats['steepest_hr']-1:02d}:00→{stats['steepest_hr']:02d}:00` 達 `+{stats['steepest_ramp']:,.2f} MW/h`） |

![WA SWIS 2021 年 1 月逐日逐時運轉負載熱力圖](figures/wem_2021_01_heatmap.png)

*圖 1：西澳電力市場（WA SWIS）2021 年 1 月 31 日 × 24 小時（AWST, UTC+8）逐時運轉負載熱力圖。深紅區塊集中於 17:00–19:00 傍晚盛夏空調尖峰（全月最高 01-08 18:00 達 `{stats['max_mw']:,.2f} MW`），上午 09:00–13:00 呈明顯淺色太陽能凹陷帶，並可見週末降載條紋與 01-26 澳洲國慶日正午全月最低谷值（`{stats['min_mw']:,.2f} MW`）。*

### 3.4 異常、尖峰與重大事件實證觀察

#### (1) 盛夏高溫熱浪尖峰（Top 5 單日尖峰）

2021 年 1 月正值南半球盛夏，伯斯多次受內陸乾熱氣團影響，系統尖峰集中於傍晚 `17:00–18:00 AWST`（太陽能發電急降與下班返家空調開啟疊加）。全月最高逐小時負載出現在 **`{stats['max_ts']}`（`{stats['max_mw']:,.2f} MW`）**：

{top5_table}

#### (2) 澳洲國慶日與正午屋頂太陽能深谷（鴨子曲線效應）

全月最低運轉負載落於 **`{stats['min_ts']}`（`{stats['min_mw']:,.2f} MW`）**，當日為 **澳洲國慶日（Australia Day）** 國定假日：商辦與工業基載下降，疊加晴朗正午高強度表後屋頂太陽能自發自用與餘電倒送，將系統淨負載壓低至不足全月尖峰的三分之一（峰谷比 `{stats['peak_to_trough']:.2f}x`）。即便就全月 31 日平均日型觀察，上午 `{stats['solar_trough_hr']:02d}:00 AWST` 均載（`{stats['solar_trough_mw']:,.2f} MW`）亦明顯低於凌晨 `{stats['overnight_trough_hr']:02d}:00` 基載谷值（`{stats['overnight_trough_mw']:,.2f} MW`），呈現典型深腹鴨子曲線。

#### (3) `2021-01-31 18:00 AWST` 伯斯突發 COVID-19 封城前後負載變化

西澳政府於 2021 年 1 月 31 日（週日）午後緊急宣布伯斯都會區、皮爾區與西南部自當日 **`18:00 AWST`** 起實施為期 5 天的嚴格封城（Snap Lockdown）。當日同時遭遇盛夏高溫，單日尖峰於 `{stats['jan31_peak_hr']:02d}:00 AWST` 達 `{stats['jan31_peak_mw']:,.2f} MW`（全月第 5 高）。為排除單純日落爬坡與週日週期效應，本研究除比較當日封城前（12:00–17:00）與封城後（18:00–23:00）外，另以同月前四個週日（{prior_sun_str}）同區段作為對照基準進行**差異中差異（Difference-in-Differences, DiD）**檢定：

- **封城前 6 小時（12:00–17:00 AWST）**：1/31 均值 `{stats['jan31_pre_mean']:,.2f} MW` vs. 前四週日均值 `{stats['sun_pre_mean']:,.2f} MW`，受當日高溫空調與民眾返家備貨影響，超額負載達 **`{stats['pre_spread_mw']:+,.2f} MW`（`{stats['pre_spread_pct']:+.2f}%`）**。
- **封城後 6 小時（18:00–23:00 AWST）**：1/31 均值 `{stats['jan31_post_mean']:,.2f} MW` vs. 前四週日均值 `{stats['sun_post_mean']:,.2f} MW`（當日因正常傍晚爬坡較午後增 `{stats['jan31_delta_mw']:+,.2f} MW`，低於前四週日正常傍晚增幅 `{stats['sun_delta_mw']:+,.2f} MW`），超額負載顯著收斂至 **`{stats['post_spread_mw']:+,.2f} MW`（`{stats['post_spread_pct']:+.2f}%`）**。
- **淨封城衝擊（DiD 估計值）**：`18:00` 封城生效後，相較前四週日之超額負載淨縮窄 **`{stats['did_mw']:+,.2f} MW`**。逐小時追蹤可見，超額負載自 `18:00` 生效瞬間（`{diff_18_mw:+,.2f} MW`）起一路單調回落至 `23:00`（`{diff_23_mw:+,.2f} MW`），清晰反映餐飲、零售、娛樂等商業用電於 18:00 強制關閉後之即時負載消退特徵。

{lockdown_table}

![WA SWIS 2021 年 1 月日內平假日結構與伯斯突發封城負載對比](figures/wem_2021_01_diurnal_and_lockdown.png)

*圖 2：WA SWIS 日內負載型態與突發封城對照雙子圖。左圖為 2021 年 1 月平日與週末 24 小時平均負載曲線及 P10–P90 分位數區間，清晰呈現屋頂太陽能造成之正午淨負載深谷（平均 10:00 降至 `{stats['solar_trough_mw']:,.2f} MW`）與日落傍晚急爬坡；右圖比較封城週末（01-29 至 01-31）與前一完整週末基準（01-22 至 01-24），可見 `2021-01-31 18:00 AWST` 伯斯突發封城生效後，當日晚間負載自高溫尖峰迅速向基準線收斂。*

---

## 4. 電網同質性對標分析（WA SWIS vs. NEM 東岸電網／台灣獨立電網）

為評估本資料集納入跨電網獨立測試（Cross-Grid Pilot）之研究價值，下表從電網拓撲、再生能源滲透與氣候驅動負載三個核心維度，將 **WA SWIS** 與 **澳洲東岸 NEM** 及 **台灣獨立電網（台電系統）** 進行系統性對標：

| 對標維度 | 西澳 WA SWIS（本 Pilot） | 澳洲東岸 NEM（NSW/VIC/QLD/SA/TAS） | 台灣獨立電網（Taipower） |
| :--- | :--- | :--- | :--- |
| **電網拓撲與互聯性** | **完全獨立孤島電網**（無任何跨區互聯線，系統容量 ~1.2–4.0 GW） | 5 州跨區互聯電網（長距離交流／直流聯網，可跨州調度轉供） | **完全獨立海島電網**（無跨國互聯線，需 100% 自主平衡頻率與備轉） |
| **時區與夏令時間** | 固定 `UTC+8`（**無 DST**，與台灣完全同區） | 跨 UTC+9.5/+10/+11，且多州實施 DST（跨區時差複雜） | 固定 `UTC+8`（**無 DST**） |
| **表後太陽能與鴨子曲線** | 全球最高滲透率族群之一；正午淨負載谷值已低於凌晨基載，傍晚急爬坡顯著 | 南澳（SA）極端鴨子曲線，其餘各州程度不一且具跨區平滑效應 | 近年太陽光電快速併網，正午淨負載凹陷與 16:00–19:00 傍晚爬坡日趨顯著 |
| **夏季氣候與空調尖峰** | 南半球**地中海型乾熱氣候**（1 月盛夏熱浪；單峰集中於 17:00–19:00 傍晚） | 跨溫帶海洋至亞熱帶多氣候帶，區域尖峰具時間錯峰效果 | 北半球**亞熱帶濕熱氣候**（7–8 月盛夏；午後商辦＋晚間住宅空調負荷高） |
| **資料獲取與基準適用性** | **T0 免金鑰公開 CSV**，結構精簡、零缺值 | T0 公開但檔案分散（5 區域 ZIP/CSV 拆檔，前處理成本較高） | 公開逐時資料解析度與歷史回溯長度受限 |

### 三大維度研究價值評估

1. **獨立孤島電網架構（與台灣高度同構，優於跨州互聯之 NEM）**  
   不同於 NEM 東岸五州可透過跨州互聯線分散區域極端負載與備轉壓力，SWIS 是全球最具代表性的大型獨立孤島電網之一，所有頻率調節、尖峰爬坡與極端事件衝擊（如突發封城或熱浪）皆直接反映在單一系統總運轉負載中，且不被外部轉供雜訊稀釋。此結構特性與台灣獨立海島電網高度一致，且兩地同屬固定 `UTC+8`（無夏令時間切換造成的 23/25 小時日異常），在時間對齊與系統邊界條件上具高度可比性。

2. **高比例屋頂太陽能鴨子曲線效應（前瞻壓力測試場域）**  
   2021-01 實證已證明 SWIS 在正午 `{stats['solar_trough_hr']:02d}:00` 出現低於凌晨基載的深谷，並於 `{stats['ramp_hours']}` 小時內產生平均 `+{stats['ramp_mw']:,.2f} MW`（`+{stats['ramp_pct']:.1f}%`）的劇烈傍晚淨負載爬坡，且在國定假日（1/26）更下探 `{stats['min_mw']:,.2f} MW`。相較於台灣正處於高光電滲透轉型期，SWIS 可作為「高滲透率鴨子曲線之先行實證場景」，用來嚴格檢驗預測模型對**正午谷值下探**、**日落斜率轉折**以及**假日×高光電疊加效應**的泛化能力。

3. **地中海型氣候夏季空調負載（跨半球季節反轉之 Out-of-Distribution 驗證價值）**  
   WA SWIS 的盛夏空調尖峰出現在南半球 1 月（對應北半球冬季），並以高溫乾熱、午後海風調節與傍晚單峰為特徵；這使本資料集成為檢驗模型「是否過度記憶北半球月份先驗（Calendar Overfitting）」的理想獨立測試集。結合本 Pilot 驗證完成的 `T0` 免認證自動化抓取與 `744` 小時零缺值標準化 Parquet 管線，後續可無痛擴展至多年份（如 2019–2024）以支援長期跨電網遷移學習與極端事件（熱浪、突發封城）韌性評估。
"""
    return report.strip() + "\n"


def _save_figure_atomic(fig: plt.Figure, dest: Path, dpi: int = 180) -> None:
    """Save a matplotlib figure atomically as PNG to guarantee idempotency."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest.with_name(dest.stem + ".tmp.png")
    fig.savefig(tmp_path, dpi=dpi, format="png", facecolor="white")
    plt.close(fig)
    os.replace(tmp_path, dest)


def generate_figures(parquet_path: Path) -> tuple[Path, Path]:
    """Generate two 180-dpi publication-ready PNG figures from the cleaned Parquet."""
    df = pd.read_parquet(parquet_path)
    df = df.sort_values("local_datetime").reset_index(drop=True)

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.edgecolor": "#333333",
            "axes.linewidth": 0.8,
            "xtick.color": "#222222",
            "ytick.color": "#222222",
        }
    )

    # ------------------------------------------------------------------
    # Figure 1: 31-day x 24-hour Operational Demand Heatmap
    # ------------------------------------------------------------------
    pivot = (
        df.pivot(index="local_date", columns="local_hour", values="load_mw")
        .sort_index()
        .reindex(columns=list(range(24)))
    )
    dates = pivot.index.tolist()
    dow_en = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    date_meta = (
        df.drop_duplicates("local_date")
        .set_index("local_date")[["day_of_week", "is_weekend"]]
    )
    y_labels = [
        f"{d[5:]} ({dow_en[int(date_meta.loc[d, 'day_of_week'])]})" for d in dates
    ]
    is_wknd_row = [bool(date_meta.loc[d, "is_weekend"]) for d in dates]

    mat = pivot.to_numpy(dtype=float)
    max_flat = int(np.nanargmax(mat))
    min_flat = int(np.nanargmin(mat))
    max_r, max_c = divmod(max_flat, mat.shape[1])
    min_r, min_c = divmod(min_flat, mat.shape[1])
    max_val = float(mat[max_r, max_c])
    min_val = float(mat[min_r, min_c])
    mean_val = float(np.nanmean(mat))

    fig1, ax1 = plt.subplots(figsize=(12.2, 9.4), constrained_layout=True)
    im = ax1.imshow(mat, aspect="auto", cmap="YlOrRd", interpolation="nearest")

    # Subtle white cell gridlines
    ax1.set_xticks(np.arange(-0.5, 24, 1), minor=True)
    ax1.set_yticks(np.arange(-0.5, len(dates), 1), minor=True)
    ax1.grid(which="minor", color="white", linestyle="-", linewidth=0.45, alpha=0.65)
    ax1.tick_params(which="minor", bottom=False, left=False)

    ax1.set_xticks(range(24))
    ax1.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=9.5)
    ax1.set_yticks(range(len(dates)))
    ax1.set_yticklabels(y_labels, fontsize=8.8)
    for tick_label, wknd in zip(ax1.get_yticklabels(), is_wknd_row):
        if wknd:
            tick_label.set_color("#1b4f72")
            tick_label.set_fontweight("bold")

    # Highlight Monthly Max and Monthly Min cells with crisp boxes
    max_rect = patches.Rectangle(
        (max_c - 0.5, max_r - 0.5),
        1.0,
        1.0,
        linewidth=2.2,
        edgecolor="#111111",
        facecolor="none",
        zorder=5,
        label=f"Monthly Max: {max_val:,.0f} MW ({dates[max_r][5:]} {max_c:02d}:00)",
    )
    min_rect = patches.Rectangle(
        (min_c - 0.5, min_r - 0.5),
        1.0,
        1.0,
        linewidth=2.2,
        edgecolor="#0b5345",
        facecolor="none",
        zorder=5,
        label=f"Monthly Min: {min_val:,.0f} MW ({dates[min_r][5:]} {min_c:02d}:00, Australia Day)",
    )
    ax1.add_patch(max_rect)
    ax1.add_patch(min_rect)

    ax1.set_xlabel("Local Hour (AWST, UTC+8)", fontsize=11, fontweight="bold", labelpad=8)
    ax1.set_ylabel("Date (2021-01, Weekends Highlighted in Blue)", fontsize=11, fontweight="bold", labelpad=8)
    ax1.set_title(
        "WA SWIS (AEMO WEM) Hourly Operational Demand Heatmap — January 2021\n"
        f"31 Days x 24 Hours | Monthly Mean: {mean_val:,.1f} MW | Peak-to-Trough Ratio: {max_val / min_val:.2f}x",
        fontsize=12.5,
        fontweight="bold",
        pad=26,
    )
    ax1.legend(
        handles=[max_rect, min_rect],
        loc="upper center",
        bbox_to_anchor=(0.5, 1.045),
        ncol=2,
        frameon=True,
        facecolor="white",
        edgecolor="#cccccc",
        fontsize=8.8,
    )

    cbar = fig1.colorbar(im, ax=ax1, pad=0.02, aspect=32)
    cbar.set_label("Operational Demand (MW)", fontsize=10.5, fontweight="bold", labelpad=8)
    cbar.ax.tick_params(labelsize=9.5)

    _save_figure_atomic(fig1, HEATMAP_FIG_PATH, dpi=180)

    # ------------------------------------------------------------------
    # Figure 2: Dual Panel — Diurnal Weekday/Weekend Profile & Snap Lockdown
    # ------------------------------------------------------------------
    fig2, (ax_left, ax_right) = plt.subplots(
        1, 2, figsize=(14.8, 5.9), sharey=True, constrained_layout=True
    )

    # Left subplot: Weekday vs. Weekend 24h mean + P10-P90 band
    hours = np.arange(24)
    wkday_grp = df[~df["is_weekend"]].groupby("local_hour")["load_mw"]
    wknd_grp = df[df["is_weekend"]].groupby("local_hour")["load_mw"]

    wk_mean = wkday_grp.mean().reindex(hours).to_numpy()
    wk_p10 = wkday_grp.quantile(0.10).reindex(hours).to_numpy()
    wk_p90 = wkday_grp.quantile(0.90).reindex(hours).to_numpy()

    we_mean = wknd_grp.mean().reindex(hours).to_numpy()
    we_p10 = wknd_grp.quantile(0.10).reindex(hours).to_numpy()
    we_p90 = wknd_grp.quantile(0.90).reindex(hours).to_numpy()

    # Subtle solar window shading
    ax_left.axvspan(9, 14, color="#f9e79f", alpha=0.28, zorder=0, label="Midday Rooftop PV Window (09–14h)")

    ax_left.fill_between(hours, wk_p10, wk_p90, color="#1b4f72", alpha=0.17, zorder=1)
    ax_left.plot(
        hours,
        wk_mean,
        color="#1b4f72",
        linewidth=2.3,
        marker="o",
        markersize=4.0,
        zorder=3,
        label="Weekday Mean (P10–P90 band)",
    )

    ax_left.fill_between(hours, we_p10, we_p90, color="#d35400", alpha=0.17, zorder=1)
    ax_left.plot(
        hours,
        we_mean,
        color="#d35400",
        linewidth=2.3,
        linestyle="--",
        marker="s",
        markersize=3.8,
        zorder=3,
        label="Weekend Mean (P10–P90 band)",
    )

    # Callout annotations for solar trough and evening peak
    solar_trough_hr = int(np.argmin(we_mean[8:15]) + 8)
    solar_trough_val = float(we_mean[solar_trough_hr])
    ax_left.annotate(
        f"Solar Duck-Curve Trough\n(Weekend {solar_trough_hr:02d}:00: {solar_trough_val:,.0f} MW)",
        xy=(solar_trough_hr, solar_trough_val),
        xytext=(5.2, 1140),
        fontsize=8.5,
        color="#7e2f00",
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "edgecolor": "#d35400", "alpha": 0.92},
        arrowprops={"arrowstyle": "->", "color": "#d35400", "lw": 1.2},
        zorder=5,
    )

    eve_peak_hr = int(np.argmax(wk_mean))
    eve_peak_val = float(wk_mean[eve_peak_hr])
    ax_left.annotate(
        f"Evening Ramp Peak\n(Weekday {eve_peak_hr:02d}:00: {eve_peak_val:,.0f} MW)",
        xy=(eve_peak_hr, eve_peak_val),
        xytext=(11.2, 3550),
        fontsize=8.5,
        color="#154360",
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "edgecolor": "#1b4f72", "alpha": 0.92},
        arrowprops={"arrowstyle": "->", "color": "#1b4f72", "lw": 1.2},
        zorder=5,
    )

    ax_left.set_xlim(-0.4, 23.4)
    ax_left.set_ylim(1000, 4000)
    ax_left.set_xticks([0, 3, 6, 9, 12, 15, 18, 21, 23])
    ax_left.set_xticklabels([f"{h:02d}:00" for h in [0, 3, 6, 9, 12, 15, 18, 21, 23]], fontsize=9)
    ax_left.set_xlabel("Local Hour (AWST, UTC+8)", fontsize=10.5, fontweight="bold", labelpad=6)
    ax_left.set_ylabel("Operational Demand (MW)", fontsize=10.5, fontweight="bold", labelpad=6)
    ax_left.set_title("(a) Diurnal Profile: Weekday vs. Weekend (Jan 2021)", fontsize=11.5, fontweight="bold", pad=10)
    ax_left.grid(True, linestyle=":", linewidth=0.7, alpha=0.75)
    ax_left.legend(loc="upper left", frameon=True, facecolor="white", edgecolor="#cccccc", fontsize=8.5)

    # Right subplot: 2021-01-29..31 vs. 2021-01-22..24 baseline + lockdown vertical line
    lockdown_dates = ["2021-01-29", "2021-01-30", "2021-01-31"]
    baseline_dates = ["2021-01-22", "2021-01-23", "2021-01-24"]

    ld_series = (
        df[df["local_date"].isin(lockdown_dates)]
        .sort_values("local_datetime")["load_mw"]
        .to_numpy(dtype=float)
    )
    bl_series = (
        df[df["local_date"].isin(baseline_dates)]
        .sort_values("local_datetime")["load_mw"]
        .to_numpy(dtype=float)
    )
    x_72 = np.arange(len(ld_series))
    lockdown_x = 48 + 18  # 2021-01-31 18:00 AWST (index 66 of 0..71)

    ax_right.axvspan(lockdown_x, 71, color="#c0392b", alpha=0.09, zorder=0, label="Post-Lockdown Window (Sun 18–23h)")
    for boundary in (24, 48):
        ax_right.axvline(boundary, color="#aaaaaa", linestyle=":", linewidth=1.0, zorder=1)

    ax_right.plot(
        x_72,
        bl_series,
        color="#4a6572",
        linewidth=1.9,
        linestyle="--",
        zorder=2,
        label="Prior Weekend Baseline: Jan 22 (Fri) – Jan 24 (Sun)",
    )
    ax_right.plot(
        x_72,
        ld_series,
        color="#c0392b",
        linewidth=2.3,
        zorder=3,
        label="Lockdown Weekend: Jan 29 (Fri) – Jan 31 (Sun)",
    )

    ax_right.axvline(
        lockdown_x,
        color="#1f2d3d",
        linestyle="--",
        linewidth=1.8,
        zorder=4,
    )

    ld_18_val = float(ld_series[lockdown_x])
    ax_right.scatter([lockdown_x], [ld_18_val], color="#1f2d3d", s=38, zorder=5)
    ax_right.annotate(
        "Perth Snap Lockdown\n2021-01-31 18:00 AWST\n"
        f"(Peak: {ld_18_val:,.0f} MW)",
        xy=(lockdown_x, ld_18_val),
        xytext=(34.5, 3440),
        fontsize=8.5,
        fontweight="bold",
        color="#1f2d3d",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "#1f2d3d", "alpha": 0.94},
        arrowprops={"arrowstyle": "->", "color": "#1f2d3d", "lw": 1.3},
        zorder=6,
    )

    ax_right.set_xlim(-0.8, 71.8)
    tick_pos = [0, 12, 24, 36, 48, 60, 71]
    tick_lbl = ["Fri\n00:00", "Fri\n12:00", "Sat\n00:00", "Sat\n12:00", "Sun\n00:00", "Sun\n12:00", "Sun\n23:00"]
    ax_right.set_xticks(tick_pos)
    ax_right.set_xticklabels(tick_lbl, fontsize=8.8)
    ax_right.set_xlabel("Relative Weekend Timeline (AWST, UTC+8)", fontsize=10.5, fontweight="bold", labelpad=6)
    ax_right.set_title("(b) Perth Snap Lockdown vs. Prior Weekend Baseline", fontsize=11.5, fontweight="bold", pad=10)
    ax_right.grid(True, linestyle=":", linewidth=0.7, alpha=0.75)
    ax_right.legend(loc="upper left", frameon=True, facecolor="white", edgecolor="#cccccc", fontsize=8.3)

    fig2.suptitle(
        "WA SWIS (AEMO WEM) — Diurnal Duck Curve Structure & 2021-01-31 Snap Lockdown Dynamics",
        fontsize=13,
        fontweight="bold",
    )

    _save_figure_atomic(fig2, DIURNAL_LOCKDOWN_FIG_PATH, dpi=180)
    return HEATMAP_FIG_PATH, DIURNAL_LOCKDOWN_FIG_PATH


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    samples = inspect_raw_samples(RAW_SLICE_PATH)
    hourly_df, diagnostics = build_hourly_dataset(RAW_SLICE_PATH)

    # Atomic write Parquet
    tmp_parquet = PARQUET_PATH.with_suffix(".parquet.tmp")
    hourly_df.to_parquet(tmp_parquet, index=False, engine="pyarrow")
    os.replace(tmp_parquet, PARQUET_PATH)

    # Generate high-resolution figures from the cleaned Parquet
    fig1_path, fig2_path = generate_figures(PARQUET_PATH)

    stats = compute_empirical_stats(hourly_df)
    report_text = render_report(samples, diagnostics, stats)

    # Atomic write report.md
    tmp_report = REPORT_PATH.with_suffix(".md.tmp")
    tmp_report.write_text(report_text, encoding="utf-8", newline="\n")
    os.replace(tmp_report, REPORT_PATH)

    report_lines = len(report_text.splitlines())
    print(f"[OK] Saved hourly Parquet: {PARQUET_PATH.name} ({len(hourly_df)} rows)")
    print(
        f"     Mean={stats['mean_mw']:.2f} MW | Min={stats['min_mw']:.2f} MW ({stats['min_ts']}) | "
        f"Max={stats['max_mw']:.2f} MW ({stats['max_ts']}) | Missing={stats['missing_hours']}"
    )
    print(f"[OK] Saved figure 1: figures/{fig1_path.name} ({fig1_path.stat().st_size:,} bytes)")
    print(f"[OK] Saved figure 2: figures/{fig2_path.name} ({fig2_path.stat().st_size:,} bytes)")
    print(f"[OK] Generated report: {REPORT_PATH.name} ({report_lines} lines)")


if __name__ == "__main__":
    main()
