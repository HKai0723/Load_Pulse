import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
FIGURES_DIR = PROJECT_ROOT / "outputs" / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

PROJECTION = ccrs.PlateCarree()


def add_base_map(ax, extent: list[float], show_states: bool = True):
    """為地圖加上真實海洋、陸地、海岸線、國界與州界底圖。"""
    ax.set_extent(extent, crs=PROJECTION)
    ax.add_feature(cfeature.OCEAN.with_scale("50m"), facecolor="#e0f2fe", zorder=0)
    ax.add_feature(cfeature.LAND.with_scale("50m"), facecolor="#f8fafc", zorder=1)
    ax.add_feature(cfeature.LAKES.with_scale("50m"), facecolor="#e0f2fe", edgecolor="#94a3b8", linewidth=0.4, zorder=2)
    ax.add_feature(cfeature.COASTLINE.with_scale("50m"), edgecolor="#475569", linewidth=0.85, zorder=3)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"), edgecolor="#64748b", linewidth=0.7, linestyle="-", zorder=3)

    if show_states:
        states_provinces = cfeature.NaturalEarthFeature(
            category="cultural",
            name="admin_1_states_provinces_lines",
            scale="50m",
            facecolor="none",
        )
        ax.add_feature(states_provinces, edgecolor="#94a3b8", linewidth=0.55, zorder=3)

    gl = ax.gridlines(draw_labels=True, linestyle=":", color="#cbd5e1", alpha=0.8, zorder=2)
    gl.top_labels = False
    gl.right_labels = False
    gl.xlabel_style = {"size": 9, "color": "#475569"}
    gl.ylabel_style = {"size": 9, "color": "#475569"}


def scale_bubble_sizes(values: list[float], min_size: float = 260, max_size: float = 1800) -> list[float]:
    arr = np.array(values, dtype=float)
    if arr.max() == arr.min():
        return [float((min_size + max_size) / 2)] * len(arr)
    norm = (arr - arr.min()) / (arr.max() - arr.min())
    return (min_size + norm * (max_size - min_size)).tolist()


def plot_denmark_map():
    raw_dk = RAW_DIR / "Denmark_Energinet" / "DK_ConsumptionCategory_RAW_202101.csv"
    dk_nodes = {
        "Nordjylland": (9.92, 57.05, "DK1", "#2563eb", (8.35, 57.25)),
        "Midtjylland": (9.50, 56.16, "DK1", "#2563eb", (8.25, 56.20)),
        "Syddanmark": (9.45, 55.35, "DK1", "#2563eb", (8.35, 54.90)),
        "Sjælland": (11.76, 55.43, "DK2", "#d97706", (12.35, 54.85)),
        "Hovedstaden": (12.45, 55.78, "DK2", "#d97706", (12.55, 56.45)),
    }

    region_means = {}
    if raw_dk.exists():
        df = pd.read_csv(raw_dk)
        utc_col = next((c for c in ["TimeUTC", "HourUTC"] if c in df.columns), None)
        if utc_col:
            df["ConsumptionkWh"] = pd.to_numeric(df["ConsumptionkWh"], errors="coerce")
            hourly_reg = df.groupby([utc_col, "RegionName"])["ConsumptionkWh"].sum(min_count=1) / 1000.0
            raw_means = hourly_reg.groupby("RegionName").mean().to_dict()
            for raw_name, val in raw_means.items():
                for key in dk_nodes:
                    if key.lower() in str(raw_name).lower():
                        region_means[key] = float(val)

    fig = plt.figure(figsize=(9.5, 7.5), dpi=150)
    ax = fig.add_subplot(1, 1, 1, projection=PROJECTION)
    add_base_map(ax, extent=[7.6, 13.6, 54.4, 57.85], show_states=False)

    names = list(dk_nodes.keys())
    mws = [region_means.get(n, 800.0) for n in names]
    sizes = scale_bubble_sizes(mws, min_size=300, max_size=1500)

    # DK1 內部連線與 DK2 內部連線
    ax.plot([9.92, 9.50, 9.45], [57.05, 56.16, 55.35], color="#3b82f6", linewidth=2.0, transform=PROJECTION, zorder=4)
    ax.plot([11.76, 12.45], [55.43, 55.78], color="#f59e0b", linewidth=2.0, transform=PROJECTION, zorder=4)

    # 大貝爾特海峽 (Great Belt) HVDC 非同步分界線
    ax.plot([10.95, 11.08], [54.75, 56.15], color="#dc2626", linestyle="--", linewidth=1.8, transform=PROJECTION, zorder=5)
    ax.text(
        10.75, 54.62, "Great Belt HVDC\n(Async Split: DK1 | DK2)",
        color="#dc2626", fontsize=8, fontweight="bold", ha="center", transform=PROJECTION,
        bbox=dict(boxstyle="round,pad=0.2", facecolor="#fef2f2", edgecolor="#fca5a5", alpha=0.95),
        zorder=6,
    )

    for (name, (lon, lat, zone, color, (lx, ly))), sz, mw in zip(dk_nodes.items(), sizes, mws):
        ax.scatter(lon, lat, s=sz, color=color, edgecolors="#0f172a", linewidths=1.2, alpha=0.88, transform=PROJECTION, zorder=6)
        mw_txt = f"\nMean: {mw:,.0f} MW" if name in region_means else ""
        ax.annotate(
            f"{name} [{zone}]{mw_txt}",
            xy=(lon, lat),
            xytext=(lx, ly),
            xycoords=PROJECTION._as_mpl_transform(ax),
            textcoords=PROJECTION._as_mpl_transform(ax),
            fontsize=8.3,
            fontweight="bold",
            ha="center",
            va="center",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor=color, linewidth=1.1, alpha=0.95),
            arrowprops=dict(arrowstyle="-", color="#475569", lw=0.9),
            zorder=7,
        )

    dk1_sum = sum(region_means.get(k, 0) for k in ["Nordjylland", "Midtjylland", "Syddanmark"])
    dk2_sum = sum(region_means.get(k, 0) for k in ["Sjælland", "Hovedstaden"])

    legend_items = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#2563eb", markeredgecolor="#0f172a",
               markersize=10, label=f"DK1 West Denmark (Continental Grid) — Mean: {dk1_sum:,.0f} MW"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#d97706", markeredgecolor="#0f172a",
               markersize=10, label=f"DK2 East Denmark (Nordic Grid) — Mean: {dk2_sum:,.0f} MW"),
    ]
    ax.legend(handles=legend_items, loc="upper left", fontsize=8.3, framealpha=0.95)
    ax.set_title("Denmark Energinet Grid Zones (DK1 vs. DK2) & 5 Regions (2021-01)", fontsize=11.5, fontweight="bold")

    fig.tight_layout()
    out_path = FIGURES_DIR / "dk_202101_region_map.png"
    fig.savefig(out_path)
    plt.close(fig)
    print(f"已產生丹麥地圖：{out_path}")


def plot_australia_map():
    au_file = PROCESSED_DIR / "AU_AEMO_NEM_hourly_202101.csv"
    means = {}
    if au_file.exists():
        df_au = pd.read_csv(au_file)
        for r in ["NSW1", "QLD1", "VIC1", "SA1", "TAS1"]:
            means[r] = float(df_au[f"{r}_load_mw"].mean())

    nem_nodes = {
        "QLD1": (145.5, -22.8, "Queensland", "#f97316", (138.5, -18.5)),
        "NSW1": (147.0, -32.2, "New South Wales", "#ef4444", (153.2, -29.5)),
        "VIC1": (144.3, -37.0, "Victoria", "#eab308", (137.0, -39.5)),
        "SA1": (135.8, -30.5, "South Australia", "#22c55e", (128.5, -33.5)),
        "TAS1": (146.6, -42.0, "Tasmania", "#3b82f6", (152.2, -42.5)),
    }

    interconnectors = [("QLD1", "NSW1"), ("NSW1", "VIC1"), ("VIC1", "SA1"), ("VIC1", "TAS1")]

    fig = plt.figure(figsize=(10.5, 7.5), dpi=150)
    ax = fig.add_subplot(1, 1, 1, projection=PROJECTION)
    add_base_map(ax, extent=[112.0, 158.0, -45.0, -10.5], show_states=True)

    # 標示非 NEM 獨立電網州別
    ax.text(121.5, -25.5, "Western Australia\n(WEM - Isolated)", fontsize=8.5, color="#64748b", ha="center", style="italic", transform=PROJECTION, zorder=4)
    ax.text(133.5, -19.5, "Northern Territory\n(Isolated Grid)", fontsize=8.5, color="#64748b", ha="center", style="italic", transform=PROJECTION, zorder=4)

    for r1, r2 in interconnectors:
        x1, y1 = nem_nodes[r1][0], nem_nodes[r1][1]
        x2, y2 = nem_nodes[r2][0], nem_nodes[r2][1]
        ax.plot([x1, x2], [y1, y2], color="#334155", linestyle="--", linewidth=1.6, transform=PROJECTION, zorder=4)

    codes = list(nem_nodes.keys())
    mws = [means.get(c, 3000.0) for c in codes]
    sizes = scale_bubble_sizes(mws, min_size=320, max_size=2000)

    for (code, (lon, lat, full_name, color, (lx, ly))), sz, mw in zip(nem_nodes.items(), sizes, mws):
        ax.scatter(lon, lat, s=sz, color=color, edgecolors="#0f172a", linewidths=1.2, alpha=0.86, transform=PROJECTION, zorder=5)
        mw_txt = f"\nMean: {mw:,.0f} MW" if code in means else ""
        ax.annotate(
            f"{code} ({full_name}){mw_txt}",
            xy=(lon, lat),
            xytext=(lx, ly),
            xycoords=PROJECTION._as_mpl_transform(ax),
            textcoords=PROJECTION._as_mpl_transform(ax),
            fontsize=8.3,
            fontweight="bold",
            ha="center",
            va="center",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor=color, linewidth=1.2, alpha=0.95),
            arrowprops=dict(arrowstyle="-", color="#475569", lw=0.9),
            zorder=6,
        )

    legend_items = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#ef4444", markeredgecolor="#0f172a",
               markersize=10, label="NEM 5 Interconnected Regions (Bubble Size = Mean MW)"),
        Line2D([0], [0], color="#334155", linestyle="--", linewidth=1.6, label="NEM Cross-Border Interconnectors"),
    ]
    ax.legend(handles=legend_items, loc="lower left", fontsize=8.3, framealpha=0.95)
    ax.set_title("Australia NEM 5 Regions, Interconnectors & Mean Load (2021-01)", fontsize=11.5, fontweight="bold")

    fig.tight_layout()
    out_path = FIGURES_DIR / "au_202101_region_map.png"
    fig.savefig(out_path)
    plt.close(fig)
    print(f"已產生澳洲地圖：{out_path}")


def plot_us_ba_map():
    us_file = PROCESSED_DIR / "US_EIA_ALL_hourly_202101.csv"
    means = {}
    if us_file.exists():
        df_us = pd.read_csv(us_file)
        for ba in ["PJM", "MISO", "ERCO", "SWPP", "CISO", "NYIS", "ISNE", "PNM"]:
            means[ba] = float(df_us[f"{ba}_load_mw"].mean())

    ba_nodes = {
        "CISO": (-119.8, 36.8, "California ISO", "#0891b2", (-121.0, 30.5)),
        "PNM": (-106.2, 34.8, "New Mexico", "#0891b2", (-109.5, 28.5)),
        "ERCO": (-98.5, 31.2, "ERCOT Texas (Isolated)", "#dc2626", (-96.5, 25.8)),
        "SWPP": (-97.5, 38.5, "Southwest Power Pool", "#2563eb", (-106.5, 43.5)),
        "MISO": (-90.5, 42.0, "Midcontinent ISO", "#2563eb", (-91.5, 47.5)),
        "PJM": (-78.5, 40.0, "Mid-Atlantic & Midwest", "#2563eb", (-75.5, 33.8)),
        "NYIS": (-75.2, 43.0, "New York ISO", "#2563eb", (-81.5, 47.5)),
        "ISNE": (-71.2, 43.5, "ISO New England", "#2563eb", (-68.5, 47.5)),
    }

    fig = plt.figure(figsize=(12, 7.2), dpi=150)
    ax = fig.add_subplot(1, 1, 1, projection=PROJECTION)
    add_base_map(ax, extent=[-127.0, -64.0, 23.5, 50.0], show_states=True)

    # 東部聯網與西部聯網示意連線
    ax.plot([-97.5, -90.5, -78.5, -75.2, -71.2], [38.5, 42.0, 40.0, 43.0, 43.5],
            color="#3b82f6", linestyle="--", linewidth=1.5, transform=PROJECTION, zorder=4)
    ax.plot([-119.8, -106.2], [36.8, 34.8], color="#06b6d4", linestyle="--", linewidth=1.5, transform=PROJECTION, zorder=4)

    codes = list(ba_nodes.keys())
    mws = [means.get(c, 20000.0) for c in codes]
    sizes = scale_bubble_sizes(mws, min_size=280, max_size=2200)

    for (code, (lon, lat, desc, color, (lx, ly))), sz, mw in zip(ba_nodes.items(), sizes, mws):
        ax.scatter(lon, lat, s=sz, color=color, edgecolors="#0f172a", linewidths=1.2, alpha=0.85, transform=PROJECTION, zorder=5)
        mw_txt = f"\nMean: {mw:,.0f} MW" if code in means else ""
        ax.annotate(
            f"{code} — {desc}{mw_txt}",
            xy=(lon, lat),
            xytext=(lx, ly),
            xycoords=PROJECTION._as_mpl_transform(ax),
            textcoords=PROJECTION._as_mpl_transform(ax),
            fontsize=8.2,
            fontweight="bold",
            ha="center",
            va="center",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor=color, linewidth=1.2, alpha=0.95),
            arrowprops=dict(arrowstyle="-", color="#475569", lw=0.9),
            zorder=6,
        )

    legend_items = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#2563eb", markeredgecolor="#0f172a",
               markersize=10, label="Eastern Interconnection (PJM, MISO, SWPP, NYIS, ISNE)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#0891b2", markeredgecolor="#0f172a",
               markersize=10, label="Western Interconnection (CISO, PNM)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#dc2626", markeredgecolor="#0f172a",
               markersize=10, label="Texas Interconnection — ERCO (Isolated Island Grid)"),
    ]
    ax.legend(handles=legend_items, loc="lower left", fontsize=8.3, framealpha=0.95)
    ax.set_title("US EIA 8 Major Balancing Authorities & Mean Load (2021-01)", fontsize=11.5, fontweight="bold")

    fig.tight_layout()
    out_path = FIGURES_DIR / "us_202101_ba_map.png"
    fig.savefig(out_path)
    plt.close(fig)
    print(f"已產生美國地圖：{out_path}")


if __name__ == "__main__":
    plot_denmark_map()
    plot_australia_map()
    plot_us_ba_map()