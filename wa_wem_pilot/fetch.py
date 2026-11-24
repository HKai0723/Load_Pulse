"""Fetch AEMO WA (WEM / SWIS) 30-minute Operational Demand CSV data for 2021-01.

Notes on WEM Trading Day boundary:
- In Western Australia's Wholesale Electricity Market (WEM / SWIS), a Trading Day
  runs from 08:00 AWST to 08:00 AWST the following morning (48 x 30-minute
  intervals, Interval-Beginning).
- Consequently, calendar timestamps 2021-01-01 00:00:00 through 07:30:00 AWST
  belong to Trading Date 2020-12-31 (Intervals 33-48) and are stored at the end
  of `operational-demand-2020.csv`.
- Fetching both `operational-demand-2020.csv` and `operational-demand-2021.csv`
  ensures complete, gap-free coverage of all 1,488 half-hour intervals in
  calendar month 2021-01 while preserving original column names and verbatim
  raw values.
"""

from __future__ import annotations

import csv
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "data" / "raw"

SOURCES: dict[int, str] = {
    2020: "https://data.wa.aemo.com.au/public/public-data/datafiles/operational-demand/operational-demand-2020.csv",
    2021: "https://data.wa.aemo.com.au/public/public-data/datafiles/operational-demand/operational-demand-2021.csv",
}

TARGET_PREFIX = "2021-01-"
SLICE_FILENAME = "operational-demand-2021-01.csv"

USER_AGENT = "Mozilla/5.0 (compatible; WA-WEM-Pilot/1.0)"
MAX_RETRIES = 4
TIMEOUT_SECONDS = 30


def download_file(url: str, dest: Path) -> int:
    """Download a URL to `dest` with retry and atomic idempotent overwrite."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest.with_suffix(dest.suffix + ".tmp")

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Unexpected HTTP status {resp.status} for {url}")
                payload = resp.read()
            if not payload:
                raise RuntimeError(f"Empty response payload from {url}")
            tmp_path.write_bytes(payload)
            os.replace(tmp_path, dest)
            return len(payload)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, RuntimeError) as exc:
            last_error = exc
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            if attempt < MAX_RETRIES:
                backoff = 2 ** (attempt - 1)
                print(f"[WARN] Attempt {attempt}/{MAX_RETRIES} failed for {url}: {exc}. Retrying in {backoff}s...")
                time.sleep(backoff)

    raise RuntimeError(f"Failed to download {url} after {MAX_RETRIES} attempts") from last_error


def extract_target_month_verbatim(raw_paths: list[Path], out_path: Path, prefix: str) -> tuple[list[str], int, dict[str, int]]:
    """Extract verbatim CSV rows whose `Trading Interval` starts with `prefix`.

    Preserves exact original column headers and unparsed string cell values.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")

    header_line: str | None = None
    header_cols: list[str] = []
    matched_lines: list[str] = []
    counts_by_file: dict[str, int] = {}

    for path in raw_paths:
        raw_text = path.read_text(encoding="utf-8-sig")
        lines = raw_text.splitlines()
        if not lines:
            raise RuntimeError(f"Raw file is empty: {path.name}")

        current_header_line = lines[0]
        current_header_cols = next(csv.reader([current_header_line]))
        if header_line is None:
            header_line = current_header_line
            header_cols = current_header_cols
        elif current_header_cols != header_cols:
            raise RuntimeError(
                f"Header mismatch in {path.name}: {current_header_cols} != {header_cols}"
            )

        ti_idx = header_cols.index("Trading Interval")
        file_count = 0
        for line in lines[1:]:
            if not line.strip():
                continue
            row = next(csv.reader([line]))
            if len(row) > ti_idx and row[ti_idx].strip().startswith(prefix):
                matched_lines.append(line)
                file_count += 1
        counts_by_file[path.name] = file_count

    if header_line is None:
        raise RuntimeError("No input CSV files processed.")

    content = "\n".join([header_line, *matched_lines]) + "\n"
    tmp_path.write_text(content, encoding="utf-8", newline="\n")
    os.replace(tmp_path, out_path)
    return header_cols, len(matched_lines), counts_by_file


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    downloaded_paths: list[Path] = []

    for year in sorted(SOURCES):
        url = SOURCES[year]
        dest = RAW_DIR / f"operational-demand-{year}.csv"
        nbytes = download_file(url, dest)
        print(f"[OK] Downloaded {dest.name} ({nbytes:,} bytes) from {url}")
        downloaded_paths.append(dest)

    slice_path = RAW_DIR / SLICE_FILENAME
    header_cols, total_rows, counts = extract_target_month_verbatim(
        downloaded_paths, slice_path, TARGET_PREFIX
    )
    print(f"[OK] Saved verbatim 2021-01 raw slice: {slice_path.name}")
    print(f"     Columns ({len(header_cols)}): {header_cols}")
    print(f"     Rows by source: {counts} -> Total 2021-01 rows: {total_rows}")


if __name__ == "__main__":
    main()
