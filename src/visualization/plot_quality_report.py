"""澳洲 AEMO NEM 全歷史 (1998–2026) 電力負載資料品質視覺化腳本。

輸入（唯讀，並驗證 Parquet 檔頭 SHA-256 Metadata）：
- data/processed/AU_AEMO_NEM_hourly_1998_2026.parquet
- data/processed/AU_AEMO_NEM_hourly_1998_2026_full_qc.parquet

輸出（outputs/figures/，高解析度英文標籤避免缺字）：
- au_1998_2026_regions_load_curve.png
- au_1998_2026_hour_dow_heatmap.png
- au_1998_2026_event_completeness.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
FIGURES_DIR = PROJECT_ROOT / "outputs" / "figures"

MAIN_PARQUET = PROCESSED_DIR / "AU_AEMO_NEM_hourly_1999_2026.parquet"
FULL_QC_PARQUET = PROCESSED_DIR / "AU_AEMO_NEM_hourly_1999_2026_full_qc.parquet"

REGIONS = ["NSW1", "QLD1", "VIC1", "SA1", "TAS1"]
REGION_COLORS = {
    "NSW1": "#dc2626",
    "QLD1": "#f97316",
    "VIC1": "#ca8a04",
    "SA1": "#16a34a",
    "TAS1": "#2563eb",
}
REGION_TITLES = {
    "NSW1": "NSW1 (Australia/Sydney)",
    "QLD1": "QLD1 (Australia/Brisbane)",
    "VIC1": "VIC1 (Australia/Melbourne)",
    "SA1": "SA1 (Australia/Adelaide)",
    "TAS1": "TAS1 (Australia/Hobart)",
}

REQUIRED_META_KEYS = [
    "pipeline_version",
    "master_sources_sha256",
    "input_raw_parquet_sha256",
    "external_holidays_sha256",
    "generated_at_utc",
]

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial", "Helvetica"]
plt.rcParams["axes.unicode_minus"] = False


def read_and_verify_metadata() -> dict[str, str]:
    """讀取並驗證兩份 Parquet 檔頭 SHA-256 Metadata 一致性。"""
    metas: dict[str, dict[str, str]] = {}
    for name, path in [("main", MAIN_PARQUET), ("full_qc", FULL_QC_PARQUET)]:
        if not path.exists():
            raise FileNotFoundError(f"Missing required Parquet file: {path}")
        schema = pq.ParquetFile(path).schema_arrow
        raw_meta = schema.metadata or {}
        meta = {
            k.decode("utf-8"): v.decode("utf-8")
            for k, v in raw_meta.items()
            if k != b"pandas"
        }
        missing = [k for k in REQUIRED_META_KEYS if k not in meta]
        if missing:
            raise KeyError(f"{path.name} missing metadata keys: {missing}")
        metas[name] = meta

    for key in ["pipeline_version", "master_sources_sha256", "input_raw_parquet_sha256"]:
        if metas["main"][key] != metas["full_qc"][key]:
            raise RuntimeError(f"Metadata mismatch between main and full_qc on {key}")

    return metas["full_qc"]


def format_footer(meta: dict[str, str]) -> str:
    return (
        f"Source: AEMO NEM (1998-12 to 2026-11) | Pipeline v{meta['pipeline_version']} | "
        f"master_sha256: {meta['master_sources_sha256'][:12]} | "
        f"raw_parquet_sha256: {meta['input_raw_parquet_sha256'][:12]}"
    )


def plot_regions_load_curve(df_main: pd.DataFrame, meta: dict[str, str]) -> Path:
    """產出 1998–2026 月均負載長期演變 + 2025 年底代表週逐時負載曲線。"""
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(15, 9.2), dpi=180, gridspec_kw={"height_ratios": [1.15, 1.0]}
    )

    # 上圖：1998–2026 各州月均負載演變
    df_m = df_main[["region_id", "timestamp_utc", "load_mw"]].copy()
    df_m["month_utc"] = df_m["timestamp_utc"].dt.tz_localize(None).dt.to_period("M").dt.to_timestamp()
    monthly = (
        df_m.groupby(["region_id", "month_utc"], observed=True)["load_mw"]
        .mean()
        .reset_index()
    )

    for region in REGIONS:
        sub = monthly.loc[monthly["region_id"] == region]
        ax1.plot(
            sub["month_utc"],
            sub["load_mw"],
            color=REGION_COLORS[region],
            linewidth=1.35,
            alpha=0.92,
            label=region,
        )

    # 標註關鍵歷史里程碑
    ax1.axvspan(
        pd.Timestamp("2020-01-30"),
        pd.Timestamp("2023-05-05"),
        color="#94a3b8",
        alpha=0.18,
        label="WHO COVID-19 Period (2020-01 to 2023-05)",
    )
    ax1.axvline(pd.Timestamp("2005-05-16"), color="#2563eb", linestyle="--", linewidth=1.1, alpha=0.8)
    ax1.text(
        pd.Timestamp("2005-08-01"),
        3400,
        "TAS1 NEM Entry\n(2005-05-16)",
        color="#1d4ed8",
        fontsize=8.5,
        fontweight="bold",
        va="top",
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#eff6ff", edgecolor="#93c5fd", alpha=0.92),
    )
    ax1.axvline(pd.Timestamp("2021-10-01"), color="#0f172a", linestyle=":", linewidth=1.3, alpha=0.85)
    ax1.text(
        pd.Timestamp("2021-11-15"),
        10600,
        "5-Min Settlement\n(2021-10-01)",
        color="#0f172a",
        fontsize=8.5,
        fontweight="bold",
        va="top",
    )

    ax1.set_title(
        "Australia NEM Regional Monthly Mean Operational Load (1998-12 to 2026-11)",
        fontsize=13,
        fontweight="bold",
        pad=10,
    )
    ax1.set_ylabel("Monthly Mean Load (MW)", fontsize=10.5)
    ax1.set_xlabel("Year (UTC)", fontsize=10)
    ax1.set_ylim(0, 11200)
    ax1.grid(True, linestyle=":", alpha=0.55)
    ax1.legend(loc="upper left", ncol=3, fontsize=8.5, framealpha=0.92)

    # 下圖：2025 代表性一週 (2025-12-22 ~ 2025-12-28 UTC) 逐時曲線，凸顯 SA1 屋頂光電鴨子曲線與負值下探
    w_start = pd.Timestamp("2025-12-22 00:00:00+00:00")
    w_end = pd.Timestamp("2025-12-28 23:00:00+00:00")
    week_df = df_main.loc[
        (df_main["timestamp_utc"] >= w_start) & (df_main["timestamp_utc"] <= w_end)
    ]

    for region in REGIONS:
        sub = week_df.loc[week_df["region_id"] == region]
        lw = 1.8 if region == "SA1" else 1.25
        ax2.plot(
            sub["timestamp_utc"],
            sub["load_mw"],
            color=REGION_COLORS[region],
            linewidth=lw,
            label=region,
        )

    ax2.axhline(0.0, color="#0f172a", linestyle="--", linewidth=1.0, alpha=0.75)

    sa_week = week_df.loc[week_df["region_id"] == "SA1"]
    sa_min_idx = sa_week["load_mw"].idxmin()
    sa_min_ts = sa_week.loc[sa_min_idx, "timestamp_utc"]
    sa_min_val = float(sa_week.loc[sa_min_idx, "load_mw"])

    ax2.scatter([sa_min_ts], [sa_min_val], color="#15803d", s=45, zorder=6)
    ax2.annotate(
        f"SA1 All-Time Hourly Min: {sa_min_val:.1f} MW\n(2025-12-25 Midday Rooftop PV Duck Curve)",
        xy=(sa_min_ts, sa_min_val),
        xytext=(pd.Timestamp("2025-12-25 14:00:00+00:00"), 2300),
        fontsize=8.5,
        fontweight="bold",
        color="#14532d",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#dcfce7", edgecolor="#16a34a", alpha=0.95),
        arrowprops=dict(arrowstyle="->", color="#15803d", lw=1.2),
        zorder=7,
    )

    ax2.set_title(
        "Representative 2025 Week Hourly Load Profile (2025-12-22 to 2025-12-28 UTC) — Midday Solar Duck Curve",
        fontsize=12.5,
        fontweight="bold",
        pad=10,
    )
    ax2.set_ylabel("Hourly Operational Load (MW)", fontsize=10.5)
    ax2.set_xlabel("Date (UTC)", fontsize=10)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax2.grid(True, linestyle=":", alpha=0.55)
    ax2.legend(loc="upper right", ncol=5, fontsize=8.5, framealpha=0.92)

    fig.text(0.5, 0.01, format_footer(meta), ha="center", fontsize=8, color="#475569")
    fig.tight_layout(rect=[0, 0.025, 1, 1])

    out_path = FIGURES_DIR / "au_1998_2026_regions_load_curve.png"
    fig.savefig(out_path, dpi=180)
    plt.close(fig)
    return out_path


def plot_hour_dow_heatmap(df_main: pd.DataFrame, meta: dict[str, str]) -> Path:
    """產出五州當地民用時間 local_hour (0–23) × day_of_week (Mon–Sun) 平均負載熱圖。"""
    fig, axes = plt.subplots(2, 3, figsize=(16, 9.4), dpi=180)
    day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    hour_ticks = [0, 4, 8, 12, 16, 20]
    hour_labels = [f"{h:02d}:00" for h in hour_ticks]

    panels = [
        ("NSW1", df_main.loc[df_main["region_id"] == "NSW1"], "NSW1 Full History (1998-2026)\nAustralia/Sydney"),
        ("QLD1", df_main.loc[df_main["region_id"] == "QLD1"], "QLD1 Full History (1998-2026)\nAustralia/Brisbane"),
        ("VIC1", df_main.loc[df_main["region_id"] == "VIC1"], "VIC1 Full History (1998-2026)\nAustralia/Melbourne"),
        ("SA1", df_main.loc[df_main["region_id"] == "SA1"], "SA1 Full History (1998-2026)\nAustralia/Adelaide"),
        ("TAS1", df_main.loc[df_main["region_id"] == "TAS1"], "TAS1 Full History (2005-2026)\nAustralia/Hobart"),
        (
            "SA1_RECENT",
            df_main.loc[(df_main["region_id"] == "SA1") & (df_main["local_date"] >= "2022-01-01")],
            "SA1 Recent Era (2022-2026)\nMidday Rooftop PV Trough",
        ),
    ]

    for idx, (_, sub, title) in enumerate(panels):
        ax = axes[idx // 3, idx % 3]
        pivot_df = sub.pivot_table(
            index="local_hour",
            columns="day_of_week",
            values="load_mw",
            aggfunc="mean",
            observed=True,
        ).reindex(index=range(24), columns=range(1, 8))

        im = ax.imshow(pivot_df.values, aspect="auto", cmap="YlOrRd")
        ax.set_title(title, fontsize=10.5, fontweight="bold", pad=8)
        ax.set_xticks(np.arange(len(day_labels)))
        ax.set_xticklabels(day_labels, fontsize=9)
        ax.set_yticks(hour_ticks)
        ax.set_yticklabels(hour_labels, fontsize=9)

        if idx % 3 == 0:
            ax.set_ylabel("Local Civil Hour (00-23)", fontsize=10)
        if idx // 3 == 1:
            ax.set_xlabel("Day of Week (ISO Mon-Sun)", fontsize=10)

        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.ax.tick_params(labelsize=8)
        cbar.set_label("Mean MW", fontsize=8.5)

    fig.suptitle(
        "Australia NEM Average Hourly Load Heatmap: Local Civil Hour vs. Day of Week (1998-2026)",
        fontsize=14,
        fontweight="bold",
        y=0.985,
    )
    fig.text(0.5, 0.01, format_footer(meta), ha="center", fontsize=8, color="#475569")
    fig.tight_layout(rect=[0, 0.025, 1, 0.96])

    out_path = FIGURES_DIR / "au_1998_2026_hour_dow_heatmap.png"
    fig.savefig(out_path, dpi=180)
    plt.close(fig)
    return out_path


def plot_event_and_completeness(df_qc: pd.DataFrame, meta: dict[str, str]) -> Path:
    """產出五分類 day_type 與疫情狀態負載對比，以及 30min→5min 時期資料完整度摘要圖。"""
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(17.6, 6.8), dpi=180, gridspec_kw={"width_ratios": [1.45, 1.0]}
    )

    # 左圖：各州五分類 day_type 相對於 WEEKDAY 基準 + COVID-19 相對於 Non-COVID 平均負載變動 (%)
    x = np.arange(len(REGIONS))
    bar_w = 0.155

    weekday_means: dict[str, float] = {}
    series_defs = [
        ("WEEKEND", "#0ea5e9", "Weekend vs. Weekday"),
        ("PUBLIC_HOLIDAY", "#2563eb", "Public Holiday vs. Weekday"),
        ("EMERGENCY_CLOSURE", "#dc2626", "Emergency Closure vs. Weekday"),
        ("BOTH", "#9333ea", "Both (Holiday & Emergency) vs. Weekday"),
        ("COVID", "#64748b", "COVID-19 (2020-2023) vs. Non-COVID"),
    ]
    deltas: dict[str, list[float]] = {k: [] for k, _, _ in series_defs}

    for region in REGIONS:
        sub = df_qc.loc[df_qc["region_id"] == region]
        base = float(sub.loc[sub["day_type"] == "WEEKDAY", "load_mw"].mean())
        weekday_means[region] = base

        for key in ("WEEKEND", "PUBLIC_HOLIDAY", "EMERGENCY_CLOSURE", "BOTH"):
            grp = sub.loc[sub["day_type"] == key, "load_mw"]
            if grp.empty or grp.isna().all():
                deltas[key].append(np.nan)
            else:
                deltas[key].append((float(grp.mean()) - base) / base * 100.0)

        cov = float(sub.loc[sub["is_covid_period"] == 1, "load_mw"].mean())
        non_cov = float(sub.loc[sub["is_covid_period"] == 0, "load_mw"].mean())
        deltas["COVID"].append((cov - non_cov) / non_cov * 100.0)

    offsets = [-2 * bar_w, -1 * bar_w, 0.0, 1 * bar_w, 2 * bar_w]
    for (key, color, label), off in zip(series_defs, offsets):
        vals = deltas[key]
        plot_vals = [0.0 if np.isnan(v) else v for v in vals]
        bars = ax1.bar(x + off, plot_vals, width=bar_w, color=color, label=label, alpha=0.92)
        for bar, orig_v in zip(bars, vals):
            if np.isnan(orig_v):
                ax1.text(
                    bar.get_x() + bar.get_width() / 2.0,
                    0.5,
                    "n=0",
                    ha="center",
                    va="bottom",
                    fontsize=6.5,
                    color="#7c3aed",
                    rotation=90,
                )
                continue
            va = "bottom" if orig_v >= 0 else "top"
            pad = 0.55 if orig_v >= 0 else -0.65
            ax1.text(
                bar.get_x() + bar.get_width() / 2.0,
                orig_v + pad,
                f"{orig_v:+.1f}%",
                ha="center",
                va=va,
                fontsize=6.7,
                fontweight="bold",
                rotation=90,
            )

    all_valid = [v for vals in deltas.values() for v in vals if not np.isnan(v)]
    y_min = min(-29.0, np.floor(min(all_valid) - 6.5))
    y_max = max(24.0, np.ceil(max(all_valid) + 12.0))

    ax1.axhline(0.0, color="#0f172a", linewidth=1.0)
    ax1.set_xticks(x)
    ax1.set_xticklabels(
        [f"{r}\n(Weekday: {weekday_means[r]:,.0f} MW)" for r in REGIONS],
        fontsize=8.6,
    )
    ax1.set_ylabel("Mean Operational Load Shift (%)", fontsize=10.5)
    ax1.set_ylim(y_min, y_max)
    ax1.set_title(
        "Mean Load Impact by 5-Class Day Type & COVID-19 Regime (1998-2026)",
        fontsize=11.5,
        fontweight="bold",
        pad=10,
    )
    ax1.grid(True, axis="y", linestyle=":", alpha=0.55)
    ax1.legend(loc="upper right", ncol=2, fontsize=7.6, framealpha=0.94)

    # 右圖：30min 時期 vs 5min 時期完整度與異常小時數對比
    era_30 = df_qc.loc[df_qc["raw_interval_min"] == 30]
    era_5 = df_qc.loc[df_qc["raw_interval_min"] == 5]

    era_labels = [
        f"30-Min Era\n(1998-12 to 2021-09)\nN = {len(era_30):,} hrs",
        f"5-Min Era\n(2021-10 to 2026-11)\nN = {len(era_5):,} hrs",
    ]
    missing_counts = [int(era_30["is_missing"].sum()), int(era_5["is_missing"].sum())]
    partial_counts = [int(era_30["is_partial_hour"].sum()), int(era_5["is_partial_hour"].sum())]
    valid_rates = [
        (len(era_30) - missing_counts[0]) / len(era_30) * 100.0,
        (len(era_5) - missing_counts[1]) / len(era_5) * 100.0,
    ]

    ex = np.arange(2)
    ew = 0.32
    eb1 = ax2.bar(ex - ew / 2, missing_counts, width=ew, color="#ef4444", label="MISSING Hours (load_mw = NaN)")
    eb2 = ax2.bar(ex + ew / 2, partial_counts, width=ew, color="#f59e0b", label="PARTIAL_HOUR (sample_count < expected)")

    for bars in (eb1, eb2):
        for bar in bars:
            h = bar.get_height()
            ax2.text(
                bar.get_x() + bar.get_width() / 2.0,
                h + 0.6,
                f"{int(h)}",
                ha="center",
                va="bottom",
                fontsize=9.5,
                fontweight="bold",
            )

    for idx, rate in enumerate(valid_rates):
        ax2.text(
            ex[idx],
            34.5,
            f"Valid Rate: {rate:.4f}%",
            ha="center",
            va="center",
            fontsize=9.2,
            fontweight="bold",
            color="#0f172a",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#e0f2fe", edgecolor="#0284c7", alpha=0.95),
        )

    ax2.set_xticks(ex)
    ax2.set_xticklabels(era_labels, fontsize=9.2)
    ax2.set_ylabel("Count of Flagged Hours (out of 1,168,495 total)", fontsize=10)
    ax2.set_ylim(0, 40)
    ax2.set_title(
        "Structural Completeness Across 30-Min to 5-Min Transition",
        fontsize=11.5,
        fontweight="bold",
        pad=10,
    )
    ax2.grid(True, axis="y", linestyle=":", alpha=0.55)
    ax2.legend(loc="upper right", fontsize=8.5, framealpha=0.94)

    dt_counts = df_qc["day_type"].value_counts().to_dict()
    summary_note = (
        f"Total Rows: {len(df_qc):,} | OK: {int((df_qc['quality_flag'] == 'OK').sum()):,} | "
        f"PARTIAL_HOUR: {int(df_qc['is_partial_hour'].sum())} | MISSING: {int(df_qc['is_missing'].sum())}\n"
        f"5-Class day_type: WEEKDAY={dt_counts.get('WEEKDAY', 0):,} | WEEKEND={dt_counts.get('WEEKEND', 0):,} | "
        f"HOLIDAY={dt_counts.get('PUBLIC_HOLIDAY', 0):,} | EMERGENCY={dt_counts.get('EMERGENCY_CLOSURE', 0):,} | "
        f"BOTH={dt_counts.get('BOTH', 0):,}"
    )
    ax2.text(
        0.5,
        -0.22,
        summary_note,
        transform=ax2.transAxes,
        ha="center",
        va="top",
        fontsize=7.8,
        color="#334155",
        bbox=dict(boxstyle="round,pad=0.35", facecolor="#f8fafc", edgecolor="#cbd5e1"),
    )

    fig.text(0.5, 0.01, format_footer(meta), ha="center", fontsize=8, color="#475569")
    fig.tight_layout(rect=[0, 0.04, 1, 1])

    out_path = FIGURES_DIR / "au_1998_2026_event_completeness.png"
    fig.savefig(out_path, dpi=180)
    plt.close(fig)
    return out_path


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    meta = read_and_verify_metadata()

    df_main = pd.read_parquet(MAIN_PARQUET, engine="pyarrow")
    df_qc = pd.read_parquet(FULL_QC_PARQUET, engine="pyarrow")

    p1 = plot_regions_load_curve(df_main, meta)
    p2 = plot_hour_dow_heatmap(df_main, meta)
    p3 = plot_event_and_completeness(df_qc, meta)

    for p in (p1, p2, p3):
        print(f"Saved: {p.name} ({p.stat().st_size / 1024:.2f} KB)")


if __name__ == "__main__":
    main()
