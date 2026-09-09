"""Load StatCan labour-force unemployment into CBA region codes."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
DEFAULT_ZIP = RAW_DIR / "14100287-eng.zip"
CSV_NAME = "14100287.csv"

# StatCan GEO label -> CBA region (Atlantic provinces kept separate until weighted).
GEO_TO_REGION = {
    "Canada": "CAN",
    "Newfoundland and Labrador": "NL",
    "Prince Edward Island": "PE",
    "Nova Scotia": "NS",
    "New Brunswick": "NB",
    "Quebec": "QC",
    "Ontario": "ON",
    "Manitoba": "MB",
    "Saskatchewan": "SK",
    "Alberta": "AB",
    "British Columbia": "BC",
}

ATLANTIC_PROVINCES = ("NL", "PE", "NS", "NB")
DIRECT_REGIONS = ("CAN", "QC", "ON", "MB", "SK", "AB", "BC")


def ensure_statcan_zip(raw_dir: Path | None = None) -> Path:
    """
    Return path to the cached full-table ZIP.

    Does not download. Place 14100287-eng.zip in data/raw/ first
    (from https://www150.statcan.gc.ca/n1/tbl/csv/14100287-eng.zip).
    """
    path = (raw_dir or RAW_DIR) / DEFAULT_ZIP.name
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path.name}. Download the full CSV ZIP for table "
            "14-10-0287-01 into data/raw/ before running the labour loader."
        )
    return path


def _read_filtered_rows(zip_path: Path) -> pd.DataFrame:
    """Stream the large CSV inside the ZIP and keep only needed rows."""
    keep_chars = {"Unemployment rate", "Labour force"}
    keep_geos = set(GEO_TO_REGION)
    chunks: list[pd.DataFrame] = []

    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(CSV_NAME) as handle:
            reader = pd.read_csv(handle, chunksize=200_000, low_memory=False)
            for chunk in reader:
                mask = (
                    chunk["GEO"].isin(keep_geos)
                    & chunk["Labour force characteristics"].isin(keep_chars)
                    & (chunk["Gender"] == "Total - Gender")
                    & (chunk["Age group"] == "15 years and over")
                    & (chunk["Statistics"] == "Estimate")
                    & (chunk["Data type"] == "Seasonally adjusted")
                )
                part = chunk.loc[
                    mask,
                    ["REF_DATE", "GEO", "Labour force characteristics", "VALUE"],
                ]
                if not part.empty:
                    chunks.append(part)

    if not chunks:
        raise ValueError(f"No matching labour rows in {zip_path}")
    return pd.concat(chunks, ignore_index=True)


def build_labour_panel(zip_path: Path | None = None) -> pd.DataFrame:
    """
    Build monthly unemployment by CBA region_code.

    Atlantic is a labour-force-weighted average of NL, PE, NS, NB.
    TERR is not created (left absent — null on join).
    Unemployment rate is kept in percent points (e.g. 7.2), as published.
    """
    path = zip_path or ensure_statcan_zip()
    raw = _read_filtered_rows(path)
    raw["region_tmp"] = raw["GEO"].map(GEO_TO_REGION)
    raw["obs_month"] = pd.to_datetime(raw["REF_DATE"] + "-01").dt.strftime("%Y-%m-%d")
    raw = raw[raw["obs_month"] >= "1995-01-01"]

    rates = raw[raw["Labour force characteristics"] == "Unemployment rate"][
        ["obs_month", "region_tmp", "VALUE"]
    ].rename(columns={"VALUE": "unemployment_rate", "region_tmp": "region_code"})
    labour_force = raw[raw["Labour force characteristics"] == "Labour force"][
        ["obs_month", "region_tmp", "VALUE"]
    ].rename(columns={"VALUE": "labour_force", "region_tmp": "region_code"})

    direct = rates[rates["region_code"].isin(DIRECT_REGIONS)].copy()

    atl = rates[rates["region_code"].isin(ATLANTIC_PROVINCES)].merge(
        labour_force[labour_force["region_code"].isin(ATLANTIC_PROVINCES)],
        on=["obs_month", "region_code"],
        how="inner",
    )
    if atl.empty:
        raise ValueError("No Atlantic province rows to weight")
    atl_w = (
        atl.assign(weighted=atl["unemployment_rate"] * atl["labour_force"])
        .groupby("obs_month", as_index=False)
        .agg(weighted=("weighted", "sum"), labour_force=("labour_force", "sum"))
    )
    atl_w["unemployment_rate"] = atl_w["weighted"] / atl_w["labour_force"]
    atl_w["region_code"] = "ATL"
    atl_out = atl_w[["region_code", "obs_month", "unemployment_rate"]]

    out = pd.concat([direct, atl_out], ignore_index=True)
    out = out.sort_values(["region_code", "obs_month"]).reset_index(drop=True)
    return out


def main() -> None:
    df = build_labour_panel()
    print(f"rows={len(df)}")
    print(df.groupby("region_code").size().to_string())
    print(df.head(5).to_string(index=False))


if __name__ == "__main__":
    main()
