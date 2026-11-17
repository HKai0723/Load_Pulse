import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
FIGURES_DIR = PROJECT_ROOT / "outputs" / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def plot_denmark_charts():
    dk_file = PROCESSED_DIR / "DK_Energinet_hourly_202101.csv"
    if not dk_file.exists():
        return

    df = pd.read_csv(dk_file)
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"])
    missing_rows = df[df["DK1_load_mw"].isna() | df["DK2_load_mw"].isna()]

    # 1. 丹麥 DK1 與 DK2 逐小時負載對比曲線
    fig, ax = plt.subplots(figsize=(14, 5.2), dpi=150)
    ax.plot(df["timestamp_utc"], df["DK1_load_mw"], color="#2563eb", linewidth=1.2, label="DK1 (West Denmark - Continental Grid)")
    ax.plot(df["timestamp_utc"], df["DK2_load_mw"], color="#d97706", linewidth=1.2, label="DK2 (East Denmark - Nordic Grid)")

    for idx, ts in enumerate(missing_rows["timestamp_utc"]):
        ax.axvline(
            ts,
            color="#dc2626",
            linestyle="--",
            linewidth=1.2,
            label="Missing Hour (NaN)" if idx == 0 else "",
        )

    ax.set_title("Denmark Energinet Zonal Hourly Electricity Load: DK1 vs. DK2 (2021-01)", fontsize=13, fontweight="bold")
    ax.set_xlabel("Date (UTC)", fontsize=11)
    ax.set_ylabel("Load (MW)", fontsize=11)
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "dk_202101_hourly_load_curve.png")
    plt.close(fig)

    # 2. 丹麥全國總負載、DK1 與 DK2 之小時 × 星期幾平均負載熱圖 (1x3 子圖)
    df["DK_TOTAL_load_mw"] = df["DK1_load_mw"] + df["DK2_load_mw"]
    panels = [
        ("DK_TOTAL", "Denmark National Total"),
        ("DK1", "DK1 (West - Continental Grid)"),
        ("DK2", "DK2 (East - Nordic Grid)"),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(15.5, 5.2), dpi=150)
    day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    hour_ticks = [0, 4, 8, 12, 16, 20]
    hour_labels = [f"{h:02d}:00" for h in hour_ticks]

    for idx, (key, title) in enumerate(panels):
        ax = axes[idx]
        pivot_df = df.pivot_table(
            index="hour",
            columns="day_of_week",
            values=f"{key}_load_mw",
            aggfunc="mean",
        ).reindex(index=range(24), columns=range(1, 8))

        im = ax.imshow(pivot_df.values, aspect="auto", cmap="YlOrRd")
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_xticks(np.arange(len(day_labels)))
        ax.set_xticklabels(day_labels, fontsize=9)
        ax.set_yticks(hour_ticks)
        ax.set_yticklabels(hour_labels, fontsize=9)
        ax.set_xlabel("Day of Week", fontsize=10)
        if idx == 0:
            ax.set_ylabel("Local Hour (Europe/Copenhagen)", fontsize=10)

        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.ax.tick_params(labelsize=8)
        cbar.set_label("MW", fontsize=8)

    fig.suptitle(
        "Denmark Average Hourly Load Heatmap: Hour vs. Day of Week (2021-01)",
        fontsize=13.5,
        fontweight="bold",
        y=0.99,
    )
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "dk_202101_hour_dow_heatmap.png")
    plt.close(fig)
    print("已更新丹麥 DK1 / DK2 品質報告圖表。")


def plot_australia_charts():
    au_file = PROCESSED_DIR / "AU_AEMO_NEM_hourly_202101.csv"
    if not au_file.exists():
        return

    df = pd.read_csv(au_file)
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"])
    regions = ["NSW1", "QLD1", "VIC1", "SA1", "TAS1"]

    fig, ax = plt.subplots(figsize=(14, 5.5), dpi=150)
    for region in regions:
        col = f"{region}_load_mw"
        if col in df.columns:
            ax.plot(df["timestamp_utc"], df[col], linewidth=1.1, label=region)

    ax.set_title("Australia NEM Regional Hourly Electricity Load (2021-01)", fontsize=13, fontweight="bold")
    ax.set_xlabel("Date (UTC)", fontsize=11)
    ax.set_ylabel("Operational Load (MW)", fontsize=11)
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(loc="upper right", ncol=5)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "au_202101_regions_load_curve.png")
    plt.close(fig)

    load_cols = [f"{r}_load_mw" for r in regions if f"{r}_load_mw" in df.columns]
    df["NEM_TOTAL_load_mw"] = df[load_cols].sum(axis=1)

    panels = [
        ("NEM_TOTAL", "NEM 5-Region Total"),
        ("NSW1", "NSW1 (New South Wales)"),
        ("QLD1", "QLD1 (Queensland)"),
        ("VIC1", "VIC1 (Victoria)"),
        ("SA1", "SA1 (South Australia)"),
        ("TAS1", "TAS1 (Tasmania)"),
    ]

    fig, axes = plt.subplots(2, 3, figsize=(15, 9), dpi=150)
    day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    hour_ticks = [0, 4, 8, 12, 16, 20]
    hour_labels = [f"{h:02d}:00" for h in hour_ticks]

    for idx, (key, title) in enumerate(panels):
        ax = axes[idx // 3, idx % 3]
        pivot_df = df.pivot_table(
            index="hour",
            columns="day_of_week",
            values=f"{key}_load_mw",
            aggfunc="mean",
        ).reindex(index=range(24), columns=range(1, 8))

        im = ax.imshow(pivot_df.values, aspect="auto", cmap="YlOrRd")
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_xticks(np.arange(len(day_labels)))
        ax.set_xticklabels(day_labels, fontsize=9)
        ax.set_yticks(hour_ticks)
        ax.set_yticklabels(hour_labels, fontsize=9)

        if idx % 3 == 0:
            ax.set_ylabel("Local Hour (AEST, UTC+10)", fontsize=10)
        if idx // 3 == 1:
            ax.set_xlabel("Day of Week", fontsize=10)

        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.ax.tick_params(labelsize=8)
        cbar.set_label("MW", fontsize=8)

    fig.suptitle(
        "Australia NEM Average Hourly Load Heatmap: Hour vs. Day of Week (2021-01)",
        fontsize=14,
        fontweight="bold",
        y=0.99,
    )
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "au_202101_hour_dow_heatmap.png")
    plt.close(fig)
    print("已更新澳洲品質報告圖表。")


def plot_us_eia_charts():
    us_file = PROCESSED_DIR / "US_EIA_ALL_hourly_202101.csv"
    if not us_file.exists():
        return

    df = pd.read_csv(us_file)
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"])

    ba_panels = [
        ("PJM", "PJM (Mid-Atlantic & Midwest)"),
        ("MISO", "MISO (Midcontinent)"),
        ("ERCO", "ERCO (ERCOT Texas)"),
        ("SWPP", "SWPP (Southwest Power Pool)"),
        ("CISO", "CISO (California ISO)"),
        ("NYIS", "NYIS (New York ISO)"),
        ("ISNE", "ISNE (ISO New England)"),
        ("PNM", "PNM (New Mexico)"),
    ]

    fig, ax = plt.subplots(figsize=(14, 5.5), dpi=150)
    for ba, _ in ba_panels:
        col = f"{ba}_load_mw"
        if col in df.columns:
            ax.plot(df["timestamp_utc"], df[col], linewidth=1.1, label=ba)

    ax.set_title("US EIA Major Balancing Authorities Hourly Load (2021-01)", fontsize=13, fontweight="bold")
    ax.set_xlabel("Date (UTC)", fontsize=11)
    ax.set_ylabel("System Demand (MW)", fontsize=11)
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(loc="upper right", ncol=4)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "us_202101_ba_load_curve.png")
    plt.close(fig)

    fig, axes = plt.subplots(2, 4, figsize=(17, 8.5), dpi=150)
    day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    hour_ticks = [0, 4, 8, 12, 16, 20]
    hour_labels = [f"{h:02d}:00" for h in hour_ticks]

    for idx, (ba, title) in enumerate(ba_panels):
        ax = axes[idx // 4, idx % 4]
        pivot_df = df.pivot_table(
            index="hour",
            columns="day_of_week",
            values=f"{ba}_load_mw",
            aggfunc="mean",
        ).reindex(index=range(24), columns=range(1, 8))

        im = ax.imshow(pivot_df.values, aspect="auto", cmap="YlOrRd")
        ax.set_title(title, fontsize=10.5, fontweight="bold")
        ax.set_xticks(np.arange(len(day_labels)))
        ax.set_xticklabels(day_labels, fontsize=8.5)
        ax.set_yticks(hour_ticks)
        ax.set_yticklabels(hour_labels, fontsize=8.5)

        if idx % 4 == 0:
            ax.set_ylabel("Hour (UTC)", fontsize=10)
        if idx // 4 == 1:
            ax.set_xlabel("Day of Week (UTC)", fontsize=9.5)

        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.ax.tick_params(labelsize=8)
        cbar.set_label("MW", fontsize=8)

    fig.suptitle(
        "US EIA Average Hourly Load Heatmap: Hour (UTC) vs. Day of Week (2021-01)",
        fontsize=14,
        fontweight="bold",
        y=0.99,
    )
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "us_202101_hour_dow_heatmap.png")
    plt.close(fig)
    print("已產生美國品質報告圖表。")


if __name__ == "__main__":
    plot_denmark_charts()
    plot_australia_charts()
    plot_us_eia_charts()