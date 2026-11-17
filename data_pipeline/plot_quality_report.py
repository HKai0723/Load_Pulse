import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PILOT_FILE = PROJECT_ROOT / "data" / "processed" / "pilot_load_hourly.csv"
FIGURES_DIR = PROJECT_ROOT / "outputs" / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def generate_quality_charts():
    df = pd.read_csv(PILOT_FILE)
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"])
    missing_rows = df[df["load_mw"].isna()]

    # 1. 逐小時負載曲線
    fig, ax = plt.subplots(figsize=(14, 5), dpi=150)
    ax.plot(df["timestamp_utc"], df["load_mw"], color="#1f77b4", linewidth=1.2, label="Hourly Load (MW)")

    for idx, ts in enumerate(missing_rows["timestamp_utc"]):
        ax.axvline(
            ts,
            color="#d62728",
            linestyle="--",
            linewidth=1.2,
            label="Missing Hour (NaN)" if idx == 0 else "",
        )

    ax.set_title("Denmark National Hourly Electricity Load (2021-01 Pilot)", fontsize=13, fontweight="bold")
    ax.set_xlabel("Date (UTC)", fontsize=11)
    ax.set_ylabel("Load (MW)", fontsize=11)
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(loc="upper right")
    fig.tight_layout()

    curve_path = FIGURES_DIR / "dk_202101_hourly_load_curve.png"
    fig.savefig(curve_path)
    plt.close(fig)
    print(f"已儲存負載曲線圖：{curve_path}")

    # 2. 小時 × 星期幾平均負載熱圖
    pivot_df = df.pivot_table(
        index="hour",
        columns="day_of_week",
        values="load_mw",
        aggfunc="mean",
    )

    fig, ax = plt.subplots(figsize=(9, 7), dpi=150)
    im = ax.imshow(pivot_df.values, aspect="auto", cmap="YlOrRd")

    day_labels = ["Mon (0)", "Tue (1)", "Wed (2)", "Thu (3)", "Fri (4)", "Sat (5)", "Sun (6)"]
    ax.set_xticks(np.arange(len(day_labels)))
    ax.set_xticklabels(day_labels)
    ax.set_yticks(np.arange(24))
    ax.set_yticklabels([f"{h:02d}:00" for h in range(24)])

    ax.set_title("Average Hourly Load Heatmap: Hour vs. Day of Week (Local Time)", fontsize=12, fontweight="bold")
    ax.set_xlabel("Day of Week", fontsize=11)
    ax.set_ylabel("Local Hour (Europe/Copenhagen)", fontsize=11)

    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Mean Load (MW)", fontsize=10)

    fig.tight_layout()
    heatmap_path = FIGURES_DIR / "dk_202101_hour_dow_heatmap.png"
    fig.savefig(heatmap_path)
    plt.close(fig)
    print(f"已儲存負載熱圖：{heatmap_path}")


if __name__ == "__main__":
    generate_quality_charts()