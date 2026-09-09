"""Phase 4: province fixed-effects regression of arrears on lagged drivers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from lags import PROVINCES, load_panel, month_over_month_changes

ROOT = Path(__file__).resolve().parents[1]
PEAKS_PATH = ROOT / "reports" / "lag_peaks.csv"
COEF_PATH = ROOT / "reports" / "regression_coefficients.csv"
FIG_DIR = ROOT / "reports" / "figures"


def median_peak_lags(peaks_path: Path | None = None) -> dict[str, int]:
    """Median across provinces of Phase 3 peak lags, per driver."""
    path = peaks_path or PEAKS_PATH
    peaks = pd.read_csv(path)
    out: dict[str, int] = {}
    for driver in ("unemployment", "policy_rate"):
        lags = peaks.loc[peaks["driver"] == driver, "peak_lag_months"]
        out[driver] = int(lags.median())
    return out


def build_regression_frame(
    panel: pd.DataFrame | None = None,
    lags: dict[str, int] | None = None,
) -> pd.DataFrame:
    """
    Levels regression frame with lagged unemployment and policy rate.

    Uses province rows only. Drops rows with any required null.
    """
    df = (panel if panel is not None else load_panel()).copy()
    lag_map = lags or median_peak_lags()
    u_lag = lag_map["unemployment"]
    p_lag = lag_map["policy_rate"]

    df = df.sort_values(["region_code", "obs_month"])
    df["unemp_lag"] = df.groupby("region_code")["unemployment_rate"].shift(u_lag)
    df["policy_lag"] = df.groupby("region_code")["policy_rate"].shift(p_lag)
    cols = ["region_code", "obs_month", "arrears_rate", "unemp_lag", "policy_lag"]
    out = df[cols].dropna().reset_index(drop=True)
    # Arrears rate as percent for readable basis-point interpretation later:
    # keep as fraction; convert in interpretation (1.0 in rate = 10000 bp of rate,
    # but unemployment is in percent points).
    return out


def fit_panel_fe(df: pd.DataFrame):
    """
    OLS with province dummies and HC1 robust standard errors.

    Formula uses C(region_code) for fixed effects.
    """
    model = smf.ols(
        "arrears_rate ~ unemp_lag + policy_lag + C(region_code)",
        data=df,
    )
    return model.fit(cov_type="HC1")


def coefficient_table(result) -> pd.DataFrame:
    """Readable coefficients for unemployment and policy only."""
    names = {
        "unemp_lag": "Lagged unemployment rate (pp)",
        "policy_lag": "Lagged policy rate (pp)",
        "Intercept": "Intercept (reference province)",
    }
    rows = []
    for key, label in names.items():
        if key not in result.params.index:
            continue
        coef = float(result.params[key])
        se = float(result.bse[key])
        rows.append(
            {
                "term": label,
                "coefficient": coef,
                "std_error": se,
                "t_stat": float(result.tvalues[key]),
                "p_value": float(result.pvalues[key]),
            }
        )
    return pd.DataFrame(rows)


def interpret_unemployment(coef: float, lag_months: int) -> str:
    """
    Plain-language sentence for the unemployment coefficient.

    Unemployment is in percent points; arrears_rate is a fraction
    (0.0022 = 0.22%). One pp of unemployment → coef change in the fraction,
    which is coef * 10000 basis points of the arrears *rate*
    (1 bp of the rate = 0.01 percentage points of arrears = 0.0001 in fraction).

    Example: coef = 0.0001 means +1 pp unemployment → +0.01 pp arrears rate
    = +1 basis point of the arrears rate.
    """
    bp = coef * 10_000  # basis points of the arrears rate
    return (
        f"A one percentage point rise in provincial unemployment is associated with a "
        f"{bp:.2f} basis point rise in the arrears rate {lag_months} months later "
        f"(holding the policy rate and province fixed)."
    )


def run_phase4() -> tuple[pd.DataFrame, dict[str, int], object, str]:
    lags = median_peak_lags()
    frame = build_regression_frame(lags=lags)
    result = fit_panel_fe(frame)
    table = coefficient_table(result)
    ROOT.joinpath("reports").mkdir(parents=True, exist_ok=True)
    table.to_csv(COEF_PATH, index=False)
    unemp_coef = float(result.params["unemp_lag"])
    paragraph = interpret_unemployment(unemp_coef, lags["unemployment"])
    return table, lags, result, paragraph


def main() -> None:
    table, lags, result, paragraph = run_phase4()
    print(f"median_lags={lags}")
    print(f"n_obs={int(result.nobs)}")
    print(table.to_string(index=False))
    print()
    print(paragraph)
    print(f"\ncoefs={COEF_PATH}")


if __name__ == "__main__":
    main()
