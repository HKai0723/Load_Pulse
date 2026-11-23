"""唯讀驗證腳本：體檢澳洲緊急停班表 (au_emergency_closures.csv) 之來源網址與電網物理訊號。

輸入（完全唯讀，絕不修改）：
- data/external/au_emergency_closures.csv (322 筆)
- data/external/au_public_holidays.csv (1,519 筆)
- data/processed/AU_AEMO_NEM_hourly_1998_2026.parquet

輸出（暫存檢核表）：
- outputs/emergency_closures_audit_temp.csv (utf-8-sig)
"""

from __future__ import annotations

import html
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EMERGENCY_CSV = PROJECT_ROOT / "data" / "external" / "au_emergency_closures.csv"
HOLIDAYS_CSV = PROJECT_ROOT / "data" / "external" / "au_public_holidays.csv"
HOURLY_PARQUET = PROJECT_ROOT / "data" / "processed" / "AU_AEMO_NEM_hourly_1998_2026.parquet"
OUTPUT_CSV = PROJECT_ROOT / "outputs" / "emergency_closures_audit_temp.csv"

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}

MAINSTREAM_MEDIA_DOMAINS = (
    "abc.net.au",
    "theguardian.com",
    "smh.com.au",
    "theage.com.au",
    "9news.com.au",
    "7news.com.au",
    "sbs.com.au",
    "news.com.au",
    "theaustralian.com.au",
    "afr.com",
    "brisbanetimes.com.au",
    "watoday.com.au",
    "reuters.com",
    "bbc.com",
    "bbc.co.uk",
    "heraldsun.com.au",
    "couriermail.com.au",
    "adelaidenow.com.au",
    "themercury.com.au",
    "canberratimes.com.au",
    "skynews.com.au",
    "theconversation.com",
)

STOPWORDS = {
    "state", "emergency", "disaster", "australia", "australian",
    "south", "north", "northern", "southern", "eastern", "western",
    "late", "early", "closure", "closures", "event", "severe",
    "extreme", "major", "crisis", "warning", "alert",
}

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def classify_source_tier(url: str) -> str:
    """依 URL 網域分類來源可信等級。"""
    if not url:
        return "OTHER"
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    if host.endswith(".gov.au") or ".gov.au" in host:
        return "GOV_OFFICIAL"
    if "wikipedia.org" in host:
        return "WIKIPEDIA"
    if any(host == dom or host.endswith("." + dom) for dom in MAINSTREAM_MEDIA_DOMAINS):
        return "MAINSTREAM_MEDIA"
    return "OTHER"


def extract_title(html_text: str) -> str:
    """自 HTML 擷取並正規化 <title> 文字。"""
    m = TITLE_RE.search(html_text)
    if not m:
        return ""
    raw_title = html.unescape(m.group(1))
    cleaned = re.sub(r"\s+", " ", raw_title).strip()
    return cleaned[:240]


def check_single_url(url: str, timeout: int = 12) -> dict[str, str]:
    """對單一不重複 source_url 發送 HTTP GET 並記錄狀態、最終網址與標題。"""
    if not url or not str(url).strip().startswith(("http://", "https://")):
        return {
            "source_url": str(url),
            "http_status": "INVALID_URL",
            "final_url": "",
            "page_title": "",
            "source_tier": "OTHER",
        }

    try:
        resp = requests.get(
            url,
            headers=REQUEST_HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )
        status_str = str(resp.status_code)
        final_url = resp.url or url
        content_type = resp.headers.get("Content-Type", "").lower()
        title = ""
        if "html" in content_type or "<title" in resp.text[:40000].lower():
            title = extract_title(resp.text[:100000])
        tier = classify_source_tier(final_url)
        if tier == "OTHER":
            tier = classify_source_tier(url)
        return {
            "source_url": url,
            "http_status": status_str,
            "final_url": final_url,
            "page_title": title,
            "source_tier": tier,
        }
    except requests.exceptions.Timeout:
        return {
            "source_url": url,
            "http_status": "TIMEOUT",
            "final_url": "",
            "page_title": "",
            "source_tier": classify_source_tier(url),
        }
    except requests.exceptions.SSLError:
        return {
            "source_url": url,
            "http_status": "SSL_ERROR",
            "final_url": "",
            "page_title": "",
            "source_tier": classify_source_tier(url),
        }
    except requests.exceptions.ConnectionError:
        return {
            "source_url": url,
            "http_status": "CONNECTION_ERROR",
            "final_url": "",
            "page_title": "",
            "source_tier": classify_source_tier(url),
        }
    except Exception as exc:
        return {
            "source_url": url,
            "http_status": f"ERROR:{type(exc).__name__}",
            "final_url": "",
            "page_title": "",
            "source_tier": classify_source_tier(url),
        }


def check_year_or_keyword_match(
    local_date: str,
    holiday_name: str,
    page_title: str,
    final_url: str,
) -> bool:
    """比對事件年份（含前後一年跨年）或事件名稱關鍵字是否出現於標題或最終網址。"""
    haystack = f"{page_title} {final_url}".lower()
    if not haystack.strip():
        return False

    year = int(local_date[:4])
    for y in (year - 1, year, year + 1):
        if str(y) in haystack:
            return True

    tokens = re.findall(r"[a-z]{4,}", holiday_name.lower())
    keywords = [t for t in tokens if t not in STOPWORDS]
    return any(kw in haystack for kw in keywords)


def compute_grid_baselines(
    df_em: pd.DataFrame,
    df_hol: pd.DataFrame,
    df_hourly: pd.DataFrame,
) -> pd.DataFrame:
    """計算各事件日之實際日均／日尖峰負載，以及前後 28 天乾淨同星期基準線變動百分比。"""
    daily = (
        df_hourly.groupby(["region_id", "local_date"], sort=True, observed=True)
        .agg(
            day_mean_mw=("load_mw", "mean"),
            day_peak_mw=("load_mw", "max"),
            day_of_week=("day_of_week", "first"),
            valid_hours=("load_mw", "count"),
        )
        .reset_index()
    )
    daily["date_dt"] = pd.to_datetime(daily["local_date"], format="%Y-%m-%d")

    excluded_keys = set(zip(df_hol["region_id"], df_hol["local_date"])) | set(
        zip(df_em["region_id"], df_em["local_date"])
    )
    daily["is_clean_day"] = [
        (r, d) not in excluded_keys and pd.notna(m)
        for r, d, m in zip(daily["region_id"], daily["local_date"], daily["day_mean_mw"])
    ]

    daily_by_region = {
        str(reg): g.sort_values("date_dt").reset_index(drop=True)
        for reg, g in daily.groupby("region_id", observed=True)
    }
    daily_lookup = {
        (str(r), str(d)): (float(m), float(p), int(dow), int(vh))
        for r, d, m, p, dow, vh in zip(
            daily["region_id"],
            daily["local_date"],
            daily["day_mean_mw"],
            daily["day_peak_mw"],
            daily["day_of_week"],
            daily["valid_hours"],
        )
    }

    records: list[dict] = []
    for row in df_em.itertuples(index=False):
        reg = str(row.region_id)
        d_str = str(row.local_date)
        ev_dt = pd.Timestamp(d_str)

        if (reg, d_str) not in daily_lookup or pd.isna(daily_lookup[(reg, d_str)][0]):
            records.append(
                {
                    "day_mean_mw": np.nan,
                    "day_peak_mw": np.nan,
                    "base_days_count": 0,
                    "base_mean_mw": np.nan,
                    "base_peak_mw": np.nan,
                    "mean_diff_pct": np.nan,
                    "peak_diff_pct": np.nan,
                }
            )
            continue

        day_mean, day_peak, dow, _ = daily_lookup[(reg, d_str)]
        reg_daily = daily_by_region[reg]
        delta_days = (reg_daily["date_dt"] - ev_dt).dt.days.abs()
        mask = (
            (delta_days > 0)
            & (delta_days <= 28)
            & (reg_daily["day_of_week"] == dow)
            & (reg_daily["is_clean_day"])
        )
        cands = reg_daily.loc[mask]

        if cands.empty:
            records.append(
                {
                    "day_mean_mw": round(day_mean, 2),
                    "day_peak_mw": round(day_peak, 2),
                    "base_days_count": 0,
                    "base_mean_mw": np.nan,
                    "base_peak_mw": np.nan,
                    "mean_diff_pct": np.nan,
                    "peak_diff_pct": np.nan,
                }
            )
            continue

        base_mean = float(cands["day_mean_mw"].mean())
        base_peak = float(cands["day_peak_mw"].mean())
        mean_diff_pct = (day_mean - base_mean) / base_mean * 100.0 if base_mean != 0 else np.nan
        peak_diff_pct = (day_peak - base_peak) / base_peak * 100.0 if base_peak != 0 else np.nan

        records.append(
            {
                "day_mean_mw": round(day_mean, 2),
                "day_peak_mw": round(day_peak, 2),
                "base_days_count": int(len(cands)),
                "base_mean_mw": round(base_mean, 2),
                "base_peak_mw": round(base_peak, 2),
                "mean_diff_pct": round(mean_diff_pct, 2),
                "peak_diff_pct": round(peak_diff_pct, 2),
            }
        )

    return pd.DataFrame(records)


def classify_risk(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """依網址狀態、來源等級、標題關鍵字比對與電網負載變動計算風險等級。"""
    levels: list[str] = []
    reasons: list[str] = []

    for row in df.itertuples(index=False):
        status = str(row.http_status)
        tier = str(row.source_tier)
        scope = str(row.scope)
        matched = bool(row.year_or_keyword_match)
        m_diff = row.mean_diff_pct
        p_diff = row.peak_diff_pct
        has_grid = pd.notna(m_diff) and pd.notna(p_diff)

        high_reasons: list[str] = []
        if status not in {"200", "403"}:
            high_reasons.append(f"HTTP_FAIL({status})")
        elif status == "200" and (not matched) and has_grid and (abs(m_diff) < 5.0 and abs(p_diff) < 7.0):
            high_reasons.append("NO_MATCH_AND_WEAK_LOAD")

        if high_reasons:
            levels.append("HIGH_RISK")
            reasons.append("|".join(high_reasons))
            continue

        check_reasons: list[str] = []
        if tier == "WIKIPEDIA":
            check_reasons.append("WIKIPEDIA_SOURCE")
        if status == "403":
            check_reasons.append("HTTP_403_BOT_BLOCK")
        if scope == "STATEWIDE" and has_grid and (abs(m_diff) < 3.0 and abs(p_diff) < 5.0):
            check_reasons.append("STATEWIDE_WEAK_LOAD")
        if not has_grid:
            check_reasons.append("OUTSIDE_GRID_RANGE")

        if check_reasons:
            levels.append("WIKI_OR_CHECK")
            reasons.append("|".join(check_reasons))
        else:
            levels.append("PASS_LIKELY")
            reasons.append("OK")

    return pd.Series(levels, dtype="string"), pd.Series(reasons, dtype="string")


def main() -> None:
    df_em = pd.read_csv(EMERGENCY_CSV, dtype=str).fillna("")
    df_hol = pd.read_csv(HOLIDAYS_CSV, dtype=str).fillna("")
    df_hourly = pd.read_parquet(
        HOURLY_PARQUET,
        columns=["region_id", "local_date", "day_of_week", "load_mw"],
        engine="pyarrow",
    )

    unique_urls = sorted(df_em["source_url"].unique().tolist())
    print(f"載入緊急停班紀錄 {len(df_em)} 筆，不重複網址 {len(unique_urls)} 筆，開始 HTTP 檢核...")

    url_results: dict[str, dict[str, str]] = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_map = {executor.submit(check_single_url, u): u for u in unique_urls}
        for fut in as_completed(future_map):
            res = fut.result()
            url_results[res["source_url"]] = res

    df_url = pd.DataFrame([url_results[u] for u in df_em["source_url"]])
    df_grid = compute_grid_baselines(df_em, df_hol, df_hourly)

    df_audit = pd.concat(
        [
            pd.DataFrame({"row_num": np.arange(1, len(df_em) + 1, dtype=np.int32)}),
            df_em.reset_index(drop=True),
            df_url[["http_status", "source_tier", "final_url", "page_title"]].reset_index(drop=True),
            df_grid.reset_index(drop=True),
        ],
        axis=1,
    )

    df_audit["year_or_keyword_match"] = [
        check_year_or_keyword_match(d, n, t, fu)
        for d, n, t, fu in zip(
            df_audit["local_date"],
            df_audit["holiday_name"],
            df_audit["page_title"],
            df_audit["final_url"],
        )
    ]

    risk_level, risk_reason = classify_risk(df_audit)
    df_audit["risk_level"] = risk_level
    df_audit["risk_reason"] = risk_reason

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df_audit.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 76)
    print(f"暫存檢核表已輸出：{OUTPUT_CSV} ({len(df_audit)} 筆)")
    print("=" * 76)
    print("HTTP 狀態分佈 (322 筆):", df_audit["http_status"].value_counts().to_dict())
    print("不重複網址 HTTP 狀態分佈:", pd.DataFrame(url_results.values())["http_status"].value_counts().to_dict())
    print("來源等級分佈 (322 筆):", df_audit["source_tier"].value_counts().to_dict())
    print("風險等級分佈 (322 筆):", df_audit["risk_level"].value_counts().to_dict())

    high_df = df_audit.loc[df_audit["risk_level"] == "HIGH_RISK"]
    print(f"\n=== HIGH_RISK 明細 (共 {len(high_df)} 筆) ===")
    if not high_df.empty:
        cols = [
            "row_num", "region_id", "local_date", "holiday_name", "scope",
            "http_status", "mean_diff_pct", "peak_diff_pct", "risk_reason", "source_url",
        ]
        print(high_df[cols].to_string(index=False))


if __name__ == "__main__":
    main()
