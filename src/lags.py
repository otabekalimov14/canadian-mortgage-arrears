"""Phase 3: cross-correlation lag analysis for arrears drivers."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "arrears.db"
PANEL_SQL = ROOT / "sql" / "01_panel.sql"
FIG_DIR = ROOT / "reports" / "figures"
TABLE_PATH = ROOT / "reports" / "lag_peaks.csv"

PROVINCES = ["ATL", "QC", "ON", "MB", "SK", "AB", "BC"]
DRIVERS = {
    "unemployment": "unemployment_rate",
    "policy_rate": "policy_rate",
    "five_year_yield": "five_year_yield",
}
MAX_LAG = 24


def load_panel(db_path: Path | None = None) -> pd.DataFrame:
    """Load the analysis panel and exclude TERR and CAN."""
    import sqlite3

    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    try:
        df = pd.read_sql_query(PANEL_SQL.read_text(), conn)
    finally:
        conn.close()
    df = df[df["region_code"].isin(PROVINCES)].copy()
    df["obs_month"] = pd.to_datetime(df["obs_month"])
    return df.sort_values(["region_code", "obs_month"]).reset_index(drop=True)


def month_over_month_changes(df: pd.DataFrame) -> pd.DataFrame:
    """First-difference arrears and each driver within region."""
    out = df.copy()
    out["arrears_mom"] = out.groupby("region_code")["arrears_rate"].diff()
    for col in DRIVERS.values():
        out[f"{col}_mom"] = out.groupby("region_code")[col].diff()
    return out


def correlation_at_lag(
    y: pd.Series,
    x: pd.Series,
    lag: int,
) -> float:
    """
    Corr(y_t, x_{t-lag}).

    Positive lag means x leads y (driver moves first).
    """
    aligned = pd.DataFrame({"y": y, "x": x.shift(lag)}).dropna()
    if len(aligned) < 24:
        return float("nan")
    if aligned["y"].std(ddof=0) == 0 or aligned["x"].std(ddof=0) == 0:
        return float("nan")
    return float(aligned["y"].corr(aligned["x"]))


def correlation_profile(
    region_df: pd.DataFrame,
    driver_col: str,
    max_lag: int = MAX_LAG,
) -> pd.DataFrame:
    """Return lag, correlation for one region and one driver MoM series."""
    y = region_df["arrears_mom"]
    x = region_df[f"{driver_col}_mom"]
    rows = [
        {"lag": lag, "correlation": correlation_at_lag(y, x, lag)}
        for lag in range(0, max_lag + 1)
    ]
    return pd.DataFrame(rows)


def peak_from_profile(profile: pd.DataFrame) -> tuple[int, float]:
    """Lag that maximises |correlation|; return that lag and signed corr."""
    clean = profile.dropna(subset=["correlation"]).copy()
    if clean.empty:
        return -1, float("nan")
    idx = clean["correlation"].abs().idxmax()
    row = clean.loc[idx]
    return int(row["lag"]), float(row["correlation"])


def compute_peak_table(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Peak lag and signed correlation by province and driver."""
    base = month_over_month_changes(df if df is not None else load_panel())
    rows: list[dict] = []
    for region in PROVINCES:
        region_df = base[base["region_code"] == region]
        for driver_name, driver_col in DRIVERS.items():
            profile = correlation_profile(region_df, driver_col)
            lag, corr = peak_from_profile(profile)
            rows.append(
                {
                    "region_code": region,
                    "driver": driver_name,
                    "peak_lag_months": lag,
                    "peak_correlation": corr,
                }
            )
    return pd.DataFrame(rows)


def plot_correlation_profile(
    region_code: str,
    driver_name: str = "unemployment",
    df: pd.DataFrame | None = None,
    out_path: Path | None = None,
) -> Path:
    """Save a bar/line chart of correlations at lags 0..24 for one province."""
    base = month_over_month_changes(df if df is not None else load_panel())
    region_df = base[base["region_code"] == region_code]
    driver_col = DRIVERS[driver_name]
    profile = correlation_profile(region_df, driver_col)
    peak_lag, peak_corr = peak_from_profile(profile)

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    path = out_path or FIG_DIR / f"lag_profile_{region_code}_{driver_name}.png"

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.axhline(0, color="black", linewidth=0.8)
    ax.plot(profile["lag"], profile["correlation"], marker="o", markersize=4)
    if peak_lag >= 0 and not np.isnan(peak_corr):
        ax.scatter([peak_lag], [peak_corr], zorder=5, s=60)
        ax.annotate(
            f"peak lag={peak_lag}, corr={peak_corr:.3f}",
            xy=(peak_lag, peak_corr),
            xytext=(peak_lag + 1.5, peak_corr),
            fontsize=9,
        )
    ax.set_xlabel("Lag (months): driver leads arrears")
    ax.set_ylabel("Correlation of month-over-month changes")
    ax.set_title(
        f"{region_code}: {driver_name} vs arrears rate (MoM changes)"
    )
    ax.set_xticks(range(0, MAX_LAG + 1, 2))
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def run_phase3() -> tuple[pd.DataFrame, Path, Path]:
    """Compute peak table and Ontario/Saskatchewan unemployment profiles."""
    panel = load_panel()
    peaks = compute_peak_table(panel)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    peaks.to_csv(TABLE_PATH, index=False)
    on_path = plot_correlation_profile("ON", "unemployment", df=panel)
    sk_path = plot_correlation_profile("SK", "unemployment", df=panel)
    return peaks, on_path, sk_path


def main() -> None:
    peaks, on_path, sk_path = run_phase3()
    print(peaks.to_string(index=False))
    print(f"\ntable={TABLE_PATH}")
    print(f"ontario_chart={on_path}")
    print(f"saskatchewan_chart={sk_path}")


if __name__ == "__main__":
    main()
