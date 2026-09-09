"""Discover and download Bank of Canada Valet macro series."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://www.bankofcanada.ca/valet"
RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
LISTS_CACHE = RAW_DIR / "valet_series_list.json"

# Confirmed against Valet labels + sample observations (Phase 2 discovery).
CONFIRMED_SERIES: dict[str, str] = {
    "overnight_target": "STATIC_ATABLE_V39079",
    "five_year_yield": "BD.CDN.5YR.DQ.YLD",
    "prime": "V80691311",
    "cpi_yoy": "STATIC_TOTALCPICHANGE",
}


def _session() -> requests.Session:
    sess = requests.Session()
    sess.headers.setdefault(
        "User-Agent",
        "canadian-mortgage-arrears/0.1 (portfolio research; python-requests)",
    )
    return sess


def fetch_series_list(
    raw_dir: Path | None = None,
    force: bool = False,
) -> dict:
    """Return Valet series metadata, caching the JSON under data/raw/."""
    directory = raw_dir or RAW_DIR
    directory.mkdir(parents=True, exist_ok=True)
    cache = directory / LISTS_CACHE.name
    if cache.exists() and not force:
        return json.loads(cache.read_text())
    response = _session().get(f"{BASE_URL}/lists/series/json", timeout=120)
    response.raise_for_status()
    payload = response.json()
    cache.write_text(json.dumps(payload))
    return payload


def search_series(needle: str, series: dict | None = None) -> list[tuple[str, str, str]]:
    """Case-insensitive substring search over code, label, and description."""
    catalog = series or fetch_series_list()["series"]
    needle_l = needle.lower()
    hits: list[tuple[str, str, str]] = []
    for code, meta in catalog.items():
        label = meta.get("label") or ""
        desc = meta.get("description") or ""
        blob = f"{code} {label} {desc}".lower()
        if needle_l in blob:
            hits.append((code, label, desc))
    return hits


def fetch_observations(series_code: str) -> tuple[str, str, pd.DataFrame]:
    """
    Download one series.

    Returns (label, description, dataframe with columns obs_date, value).
    """
    response = _session().get(
        f"{BASE_URL}/observations/{series_code}/json",
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    detail = payload.get("seriesDetail", {}).get(series_code, {})
    label = detail.get("label") or series_code
    description = detail.get("description") or ""
    rows: list[dict] = []
    for obs in payload.get("observations", []):
        cell = obs.get(series_code)
        if isinstance(cell, dict):
            raw = cell.get("v")
        else:
            raw = cell
        if raw is None or raw == "":
            continue
        rows.append({"obs_date": obs["d"], "value": float(raw)})
    return label, description, pd.DataFrame(rows)


def peek_series(series_code: str, n: int = 5) -> None:
    """Print label and first/last observations for a candidate code."""
    label, description, df = fetch_observations(series_code)
    print(f"code={series_code}")
    print(f"label={label}")
    print(f"description={description}")
    if df.empty:
        print("observations=(none)")
        return
    print(f"n={len(df)} first={df.iloc[0].to_dict()} last={df.iloc[-1].to_dict()}")
    print("first_rows:")
    print(df.head(n).to_string(index=False))
    print("last_rows:")
    print(df.tail(n).to_string(index=False))


def discover() -> None:
    """Print confirmed series with live peeks (for re-verification)."""
    print("=== Confirmed Valet series ===\n")
    for name, code in CONFIRMED_SERIES.items():
        print(f"## {name}")
        peek_series(code, n=3)
        print()


def load_macro_long(series_map: dict[str, str] | None = None) -> pd.DataFrame:
    """
    Pull confirmed series into long format for the macro table.

    Columns: series_code, series_label, obs_date, value
    (native Valet frequency — daily or monthly).
    """
    mapping = series_map or CONFIRMED_SERIES
    frames: list[pd.DataFrame] = []
    for _name, code in mapping.items():
        label, _desc, df = fetch_observations(code)
        if df.empty:
            raise ValueError(f"No observations returned for {code}")
        piece = df.copy()
        piece["series_code"] = code
        piece["series_label"] = label
        frames.append(piece[["series_code", "series_label", "obs_date", "value"]])
    out = pd.concat(frames, ignore_index=True)
    return out.sort_values(["series_code", "obs_date"]).reset_index(drop=True)


def monthly_last_observation(macro: pd.DataFrame) -> pd.DataFrame:
    """
    Downsample to one value per calendar month: last available observation.

    Returns columns series_code, series_label, obs_month (YYYY-MM-01), value.
    """
    df = macro.copy()
    df["obs_month"] = pd.to_datetime(df["obs_date"]).dt.to_period("M").dt.to_timestamp()
    df = df.sort_values(["series_code", "obs_date"])
    monthly = (
        df.groupby(["series_code", "series_label", "obs_month"], as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )
    monthly["obs_month"] = monthly["obs_month"].dt.strftime("%Y-%m-%d")
    return monthly[["series_code", "series_label", "obs_month", "value"]]


def main() -> None:
    discover()
    macro = load_macro_long()
    print(f"macro_rows={len(macro)}")
    print(macro.groupby("series_code").size().to_string())


if __name__ == "__main__":
    main()
