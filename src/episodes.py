"""Phase 5: align GFC and recent arrears episodes on national troughs."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "arrears.db"
FIG_PATH = ROOT / "reports" / "figures" / "episodes_aligned.png"
SUMMARY_PATH = ROOT / "reports" / "episode_comparison.txt"

PROVINCES = ["ATL", "QC", "ON", "MB", "SK", "AB", "BC"]
GFC_WINDOW = ("2007-01-01", "2010-12-01")
RECENT_WINDOW_START = "2021-01-01"
HORIZON = 24
SPEED_HORIZON = 18


def load_arrears(db_path: Path | None = None) -> pd.DataFrame:
    import sqlite3

    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    try:
        df = pd.read_sql_query(
            """
            SELECT region_code, obs_month, arrears_rate
            FROM arrears
            WHERE arrears_rate IS NOT NULL
            """,
            conn,
        )
    finally:
        conn.close()
    df["obs_month"] = pd.to_datetime(df["obs_month"])
    return df.sort_values(["region_code", "obs_month"]).reset_index(drop=True)


def find_trough(
    df: pd.DataFrame,
    start: str,
    end: str | None = None,
    region: str = "CAN",
) -> pd.Timestamp:
    """Month of minimum national arrears rate in [start, end]."""
    can = df[df["region_code"] == region].copy()
    mask = can["obs_month"] >= pd.Timestamp(start)
    if end is not None:
        mask &= can["obs_month"] <= pd.Timestamp(end)
    window = can.loc[mask]
    if window.empty:
        raise ValueError(f"No {region} rows in window {start}..{end}")
    idx = window["arrears_rate"].idxmin()
    return pd.Timestamp(window.loc[idx, "obs_month"])


def aligned_episode(
    df: pd.DataFrame,
    trough: pd.Timestamp,
    regions: list[str],
    horizon: int = HORIZON,
) -> pd.DataFrame:
    """
    Arrears rate relative to each region's own trough-month level.

    month_index 0 = trough month. Values are ratio to own level at trough
    (1.0 = unchanged).
    """
    rows: list[dict] = []
    for region in regions:
        g = df[df["region_code"] == region].set_index("obs_month").sort_index()
        if trough not in g.index:
            continue
        base = float(g.loc[trough, "arrears_rate"])
        if base == 0 or pd.isna(base):
            continue
        for k in range(0, horizon + 1):
            month = trough + pd.DateOffset(months=k)
            if month not in g.index:
                break
            rate = float(g.loc[month, "arrears_rate"])
            rows.append(
                {
                    "region_code": region,
                    "trough": trough,
                    "month_index": k,
                    "obs_month": month,
                    "arrears_rate": rate,
                    "relative_to_trough": rate / base,
                }
            )
    return pd.DataFrame(rows)


def national_change(
    df: pd.DataFrame,
    trough: pd.Timestamp,
    months: int = SPEED_HORIZON,
) -> tuple[float, float, float, pd.Timestamp]:
    """
    Absolute change in CAN arrears rate from trough to trough+months
    (or last available month if shorter).
    """
    can = df[df["region_code"] == "CAN"].set_index("obs_month").sort_index()
    start_rate = float(can.loc[trough, "arrears_rate"])
    target = trough + pd.DateOffset(months=months)
    available = can.index[can.index >= trough]
    end_month = target if target in can.index else available.max()
    # If target is past sample, use last; if target missing mid-sample, use last <= target
    if target not in can.index:
        prior = can.index[(can.index >= trough) & (can.index <= target)]
        end_month = prior.max() if len(prior) else available.max()
    end_rate = float(can.loc[end_month, "arrears_rate"])
    return start_rate, end_rate, end_rate - start_rate, pd.Timestamp(end_month)


def plot_episodes(
    gfc: pd.DataFrame,
    recent: pd.DataFrame,
    out_path: Path | None = None,
) -> Path:
    """One figure: two panels, provinces relative to own trough level."""
    path = out_path or FIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)
    for ax, data, title in (
        (axes[0], gfc, "GFC episode (aligned on national trough)"),
        (axes[1], recent, "Recent episode (aligned on national trough)"),
    ):
        for region in PROVINCES:
            sub = data[data["region_code"] == region]
            if sub.empty:
                continue
            ax.plot(
                sub["month_index"],
                sub["relative_to_trough"],
                label=region,
                linewidth=1.4,
            )
        ax.axhline(1.0, color="black", linewidth=0.8, linestyle="--")
        ax.set_xlabel("Months since trough")
        ax.set_title(title)
        ax.set_xlim(0, HORIZON)
    axes[0].set_ylabel("Arrears rate / own rate at trough")
    axes[1].legend(loc="upper left", fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def composition_sentence() -> str:
    return (
        "Between the two episodes the reporting panel changed: Manulife joined in "
        "2004, Laurentian in October 2010 (after the GFC trough window’s early "
        "months), and Equitable in November 2020, so the recent cycle includes "
        "banks that were not in the GFC-era panel."
    )


def write_summary(
    gfc_trough: pd.Timestamp,
    recent_trough: pd.Timestamp,
    gfc_delta: float,
    recent_delta: float,
    gfc_end: pd.Timestamp,
    recent_end: pd.Timestamp,
    path: Path | None = None,
) -> str:
    """Paragraph on faster/slower plus composition sentence."""
    gfc_bp = gfc_delta * 10_000
    recent_bp = recent_delta * 10_000
    if abs(recent_bp) > abs(gfc_bp) * 1.1:
        speed = "faster"
    elif abs(recent_bp) < abs(gfc_bp) * 0.9:
        speed = "slower"
    else:
        speed = "similar"

    paragraph = (
        f"National arrears bottomed in {gfc_trough.strftime('%Y-%m')} (GFC window) "
        f"and {recent_trough.strftime('%Y-%m')} (recent window). From trough to "
        f"roughly 18 months later ({gfc_end.strftime('%Y-%m')} vs "
        f"{recent_end.strftime('%Y-%m')}), the national arrears rate rose by "
        f"{gfc_bp:.1f} basis points after the GFC trough and by {recent_bp:.1f} "
        f"basis points after the recent trough, so the current cycle looks "
        f"{speed} over that horizon. "
        f"{composition_sentence()}"
    )
    out = path or SUMMARY_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(paragraph + "\n")
    return paragraph


def run_phase5() -> tuple[pd.Timestamp, pd.Timestamp, Path, str]:
    df = load_arrears()
    gfc_trough = find_trough(df, GFC_WINDOW[0], GFC_WINDOW[1])
    recent_trough = find_trough(df, RECENT_WINDOW_START, None)

    gfc = aligned_episode(df, gfc_trough, PROVINCES)
    recent = aligned_episode(df, recent_trough, PROVINCES)
    fig = plot_episodes(gfc, recent)

    gfc_start, gfc_end_rate, gfc_delta, gfc_end = national_change(df, gfc_trough)
    recent_start, recent_end_rate, recent_delta, recent_end = national_change(
        df, recent_trough
    )
    _ = (gfc_start, gfc_end_rate, recent_start, recent_end_rate)
    paragraph = write_summary(
        gfc_trough, recent_trough, gfc_delta, recent_delta, gfc_end, recent_end
    )
    return gfc_trough, recent_trough, fig, paragraph


def main() -> None:
    gfc_trough, recent_trough, fig, paragraph = run_phase5()
    print(f"gfc_trough={gfc_trough.date()}")
    print(f"recent_trough={recent_trough.date()}")
    print(f"figure={fig}")
    print(paragraph)


if __name__ == "__main__":
    main()
