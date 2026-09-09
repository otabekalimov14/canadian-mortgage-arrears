"""Golden-value and structural tests for CBA arrears PDF parsing."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fetch_cba import download_latest, report_month_from_filename  # noqa: E402
from parse_cba import (  # noqa: E402
    REGION_CODES,
    add_computed_rate,
    parse_pdf,
    report_month,
)

PDF_PATH = ROOT / "data" / "raw"


@pytest.fixture(scope="module")
def arrears_df() -> pd.DataFrame:
    pdf = download_latest(raw_dir=PDF_PATH)
    return add_computed_rate(parse_pdf(pdf))


@pytest.fixture(scope="module")
def end_month(arrears_df: pd.DataFrame) -> str:
    return report_month(arrears_df)


def _lookup(
    df: pd.DataFrame, region: str, month: str
) -> pd.Series:
    hit = df[(df["region_code"] == region) & (df["obs_month"] == month)]
    assert len(hit) == 1, f"expected one row for {region} {month}, got {len(hit)}"
    return hit.iloc[0]


@pytest.mark.parametrize(
    "region,month,total,arrears,printed",
    [
        ("CAN", "2025-03-01", 4_983_931, 11_003, 0.0022),
        ("ON", "2025-03-01", 2_184_633, 4_367, 0.0020),
        ("SK", "2025-03-01", 123_523, 672, 0.0054),
        ("QC", "2025-03-01", 930_998, 1_697, 0.0018),
        ("CAN", "1995-01-01", 2_184_443, 11_014, 0.0050),
    ],
)
def test_golden_values(
    arrears_df: pd.DataFrame,
    region: str,
    month: str,
    total: int,
    arrears: int,
    printed: float,
) -> None:
    row = _lookup(arrears_df, region, month)
    assert int(row["total_mortgages"]) == total
    assert int(row["mortgages_arrears"]) == arrears
    assert row["printed_rate"] == pytest.approx(printed, abs=1e-6)
    assert row["arrears_rate"] == pytest.approx(arrears / total, rel=0, abs=1e-12)


def test_all_regions_present(arrears_df: pd.DataFrame) -> None:
    assert set(arrears_df["region_code"]) == set(REGION_CODES)


def test_no_duplicate_months(arrears_df: pd.DataFrame) -> None:
    dupes = arrears_df.duplicated(subset=["region_code", "obs_month"]).sum()
    assert dupes == 0


def test_continuous_months(arrears_df: pd.DataFrame, end_month: str) -> None:
    expected = pd.date_range("1995-01-01", end_month, freq="MS").strftime("%Y-%m-%d")
    for code, group in arrears_df.groupby("region_code"):
        months = group["obs_month"].tolist()
        assert months == list(expected), f"{code} month index mismatch"


def test_row_counts_match_span(arrears_df: pd.DataFrame, end_month: str) -> None:
    n_months = len(pd.date_range("1995-01-01", end_month, freq="MS"))
    counts = arrears_df.groupby("region_code").size()
    for code in REGION_CODES:
        assert counts[code] == n_months


def test_region_totals_reconcile_to_canada(arrears_df: pd.DataFrame) -> None:
    sub = arrears_df[arrears_df["region_code"] != "CAN"].copy()
    # Null TERR total counts as 0 for reconciliation only.
    sub["total_for_sum"] = sub["total_mortgages"].fillna(0)
    summed = sub.groupby("obs_month")["total_for_sum"].sum()
    canada = arrears_df[arrears_df["region_code"] == "CAN"].set_index("obs_month")[
        "total_mortgages"
    ]
    frame = pd.DataFrame({"summed": summed, "canada": canada}).dropna(subset=["canada"])
    rel = (frame["summed"] - frame["canada"]).abs() / frame["canada"]
    worst = float(rel.max())
    within = float((rel <= 0.003).mean())
    # Source PDF is not perfectly additive every month; catch decade-mix errors.
    assert worst <= 0.03, f"max relative gap {worst:.6f} exceeds 3%"
    assert within >= 0.99, f"only {within:.1%} of months within 0.3%"


def test_computed_rates_in_band(arrears_df: pd.DataFrame) -> None:
    rates = arrears_df["arrears_rate"].dropna()
    assert (rates >= 0.0005).all()
    assert (rates <= 0.02).all()


def test_territories_suppressed_are_null(arrears_df: pd.DataFrame) -> None:
    terr = arrears_df[arrears_df["region_code"] == "TERR"]
    # At least some months should have suppressed arrears (asterisks -> null).
    assert terr["mortgages_arrears"].isna().any()
    # Null arrears must not become zero.
    assert not ((terr["mortgages_arrears"] == 0) & terr["printed_rate"].isna()).any()


def test_printed_rate_close_to_computed(arrears_df: pd.DataFrame) -> None:
    both = arrears_df.dropna(subset=["printed_rate", "arrears_rate"])
    # Printed is rounded to 2 decimals of percent; source has occasional typos.
    gap = (both["printed_rate"] - both["arrears_rate"]).abs()
    close_share = float((gap < 0.0001 + 1e-9).mean())
    assert close_share >= 0.99, f"only {close_share:.1%} of rows within rounding tolerance"


def test_report_month_matches_filename() -> None:
    pdf = download_latest(raw_dir=PDF_PATH)
    df = add_computed_rate(parse_pdf(pdf))
    assert report_month(df) == report_month_from_filename(pdf.name)
