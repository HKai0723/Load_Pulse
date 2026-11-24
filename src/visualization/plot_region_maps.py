"""澳洲 AEMO NEM 五大調度區全歷史 (1998–2026) 地理分佈與統計摘要地圖。

輸入（唯讀，並驗證 Parquet 檔頭 SHA-256 Metadata）：
- data/processed/AU_AEMO_NEM_hourly_1998_2026.parquet
- data/processed/AU_AEMO_NEM_hourly_1998_2026_full_qc.parquet

輸出（outputs/figures/，高解析度英文標籤避免缺字）：
- au_1998_2026_region_map.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from matplotlib.lines import Line2D

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
FIGURES_DIR = PROJECT_ROOT / "outputs" / "figures"

MAIN_PARQUET = PROCESSED_DIR / "AU_AEMO_NEM_hourly_1999_2026.parquet"
FULL_QC_PARQUET = PROCESSED_DIR / "AU_AEMO_NEM_hourly_1999_2026_full_qc.parquet"

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

PROJECTION = ccrs.PlateCarree()


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


def add_base_map(ax, extent: list[float], show_states: bool = True) -> None:
    """加上海洋、陸地、湖泊、海岸線、國界與州界底圖。"""
    ax.set_extent(extent, crs=PROJECTION)
    ax.add_feature(cfeature.OCEAN.with_scale("50m"), facecolor="#e0f2fe", zorder=0)
    ax.add_feature(cfeature.LAND.with_scale("50m"), facecolor="#f8fafc", zorder=1)
    ax.add_feature(
        cfeature.LAKES.with_scale("50m"),
        facecolor="#e0f2fe",
        edgecolor="#94a3b8",
        linewidth=0.4,
        zorder=2,
    )
    ax.add_feature(cfeature.COASTLINE.with_scale("50m"), edgecolor="#475569", linewidth=0.85, zorder=3)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"), edgecolor="#64748b", linewidth=0.7, zorder=3)

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
    gl.xlabel_style = {"size": 8.5, "color": "#475569"}
    gl.ylabel_style = {"size": 8.5, "color": "#475569"}


def scale_bubble_sizes(values: list[float], min_size: float = 380, max_size: float = 2100) -> list[float]:
    arr = np.array(values, dtype=float)
    if arr.max() == arr.min():
        return [float((min_size + max_size) / 2)] * len(arr)
    norm = (arr - arr.min()) / (arr.max() - arr.min())
    return (min_size + norm * (max_size - min_size)).tolist()


def plot_australia_full_history_map() -> Path:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    meta = read_and_verify_metadata()

    df_qc = pd.read_parquet(
        FULL_QC_PARQUET,
        columns=["region_id", "timestamp_utc", "local_date", "load_mw", "is_missing", "iana_tz"],
        engine="pyarrow",
    )

    stats: dict[str, dict] = {}
    for region, g in df_qc.groupby("region_id", sort=True, observed=True):
        valid = g["load_mw"].dropna()
        total_h = int(len(g))
        miss_h = int(g["is_missing"].sum())
        stats[str(region)] = {
            "start_ym": str(g["local_date"].min())[:7],
            "end_ym": str(g["local_date"].max())[:7],
            "hours": total_h,
            "completeness": (total_h - miss_h) / total_h * 100.0,
            "mean_mw": float(valid.mean()),
            "min_mw": float(valid.min()),
            "max_mw": float(valid.max()),
            "iana_tz": str(g["iana_tz"].iloc[0]),
        }

    nem_nodes = {
        "QLD1": (145.5, -22.8, "Queensland", "#f97316", (151.0, -15.6)),
        "NSW1": (147.0, -32.2, "New South Wales", "#dc2626", (155.5, -28.0)),
        "VIC1": (144.3, -37.0, "Victoria", "#ca8a04", (135.5, -40.8)),
        "SA1": (135.8, -30.5, "South Australia", "#16a34a", (123.5, -34.2)),
        "TAS1": (146.6, -42.0, "Tasmania", "#2563eb", (155.5, -41.5)),
    }
    interconnectors = [("QLD1", "NSW1"), ("NSW1", "VIC1"), ("VIC1", "SA1"), ("VIC1", "TAS1")]

    fig = plt.figure(figsize=(13.5, 8.6), dpi=180)
    ax = fig.add_subplot(1, 1, 1, projection=PROJECTION)
    add_base_map(ax, extent=[111.5, 163.5, -46.0, -10.0], show_states=True)

    # 非 NEM 獨立電網州別標註
    ax.text(
        121.5,
        -24.8,
        "Western Australia\n(WEM - Isolated Grid)",
        fontsize=8.5,
        color="#64748b",
        ha="center",
        style="italic",
        transform=PROJECTION,
        zorder=4,
    )
    ax.text(
        133.5,
        -19.2,
        "Northern Territory\n(Isolated Grid)",
        fontsize=8.5,
        color="#64748b",
        ha="center",
        style="italic",
        transform=PROJECTION,
        zorder=4,
    )

    for r1, r2 in interconnectors:
        x1, y1 = nem_nodes[r1][0], nem_nodes[r1][1]
        x2, y2 = nem_nodes[r2][0], nem_nodes[r2][1]
        ax.plot([x1, x2], [y1, y2], color="#334155", linestyle="--", linewidth=1.7, transform=PROJECTION, zorder=4)

    codes = list(nem_nodes.keys())
    mws = [stats[c]["mean_mw"] for c in codes]
    sizes = scale_bubble_sizes(mws, min_size=380, max_size=2100)

    for (code, (lon, lat, full_name, color, (lx, ly))), sz in zip(nem_nodes.items(), sizes):
        st = stats[code]
        ax.scatter(
            lon,
            lat,
            s=sz,
            color=color,
            edgecolors="#0f172a",
            linewidths=1.2,
            alpha=0.86,
            transform=PROJECTION,
            zorder=5,
        )
        label_text = (
            f"{code} ({full_name})\n"
            f"{st['start_ym']} to {st['end_ym']} | {st['hours']:,} hrs\n"
            f"Mean: {st['mean_mw']:,.0f} | Min: {st['min_mw']:,.0f} | Max: {st['max_mw']:,.0f} MW\n"
            f"Completeness: {st['completeness']:.4f}%"
        )
        ax.annotate(
            label_text,
            xy=(lon, lat),
            xytext=(lx, ly),
            xycoords=PROJECTION._as_mpl_transform(ax),
            textcoords=PROJECTION._as_mpl_transform(ax),
            fontsize=7.6,
            fontweight="bold",
            ha="center",
            va="center",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=color, linewidth=1.3, alpha=0.95),
            arrowprops=dict(arrowstyle="-", color="#475569", lw=1.0),
            zorder=6,
        )

    legend_items = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor="#dc2626",
            markeredgecolor="#0f172a",
            markersize=10,
            label="NEM 5 Interconnected Regions (Bubble Area ~ Full-History Mean MW)",
        ),
        Line2D(
            [0],
            [0],
            color="#334155",
            linestyle="--",
            linewidth=1.7,
            label="NEM Cross-Border Interconnectors",
        ),
    ]
    ax.legend(handles=legend_items, loc="lower left", fontsize=8.3, framealpha=0.95)
    ax.set_title(
        "Australia NEM 5 Regions — Full-History Coverage, Load Statistics & Completeness (1998-2026)",
        fontsize=12.5,
        fontweight="bold",
        pad=10,
    )

    footer = (
        f"Total Hourly Rows: {len(df_qc):,} | Pipeline v{meta['pipeline_version']} | "
        f"master_sha256: {meta['master_sources_sha256'][:12]} | "
        f"raw_parquet_sha256: {meta['input_raw_parquet_sha256'][:12]}"
    )
    fig.text(0.5, 0.012, footer, ha="center", fontsize=8, color="#475569")
    fig.tight_layout(rect=[0, 0.028, 1, 1])

    out_path = FIGURES_DIR / "au_1998_2026_region_map.png"
    fig.savefig(out_path, dpi=180)
    plt.close(fig)
    print(f"Saved: {out_path.name} ({out_path.stat().st_size / 1024:.2f} KB)")
    return out_path


if __name__ == "__main__":
    plot_australia_full_history_map()
