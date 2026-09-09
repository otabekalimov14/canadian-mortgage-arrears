"""Create SQLite DB and load arrears, macro, labour, and coverage breaks."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from fetch_boc import load_macro_long
from fetch_cba import cached_pdf_path, download_latest
from load_statcan import build_labour_panel, ensure_statcan_zip
from parse_cba import load_arrears_frame, report_month

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "sql" / "schema.sql"
DB_PATH = ROOT / "data" / "arrears.db"
PANEL_SQL_PATH = ROOT / "sql" / "01_panel.sql"

REGIONS = [
    ("CAN", "Canada", 1),
    ("ATL", "Atlantic", 0),
    ("QC", "Quebec", 0),
    ("ON", "Ontario", 0),
    ("MB", "Manitoba", 0),
    ("SK", "Saskatchewan", 0),
    ("AB", "Alberta", 0),
    ("BC", "British Columbia", 0),
    ("TERR", "Territories", 0),
]

# Coverage / reporting breaks from PROJECT_BRIEF.md section 4.
BREAKS = [
    (None, "2004-04-01", "Manulife Bank joins reporting panel"),
    ("QC", "2010-10-01", "Laurentian Bank joins; Quebec mortgage count jumps"),
    (None, "2010-10-01", "Laurentian Bank joins reporting panel"),
    (None, "2020-11-01", "Equitable Bank joins reporting panel"),
    ("MB", "2006-11-01", "Reporting adjustment to Manitoba figures"),
    ("SK", "2006-11-01", "Reporting adjustment to Saskatchewan figures"),
]


def create_schema(conn: sqlite3.Connection, schema_path: Path = SCHEMA_PATH) -> None:
    conn.executescript(schema_path.read_text())


def load_regions(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO region (region_code, region_name, is_national) VALUES (?, ?, ?)",
        REGIONS,
    )


def load_breaks(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO breaks (region_code, obs_month, reason) VALUES (?, ?, ?)",
        BREAKS,
    )


def load_arrears(conn: sqlite3.Connection, df: pd.DataFrame) -> None:
    cols = [
        "region_code",
        "obs_month",
        "total_mortgages",
        "mortgages_arrears",
        "arrears_rate",
        "printed_rate",
    ]
    payload = df[cols].where(pd.notnull(df[cols]), None)
    conn.executemany(
        """
        INSERT INTO arrears (
            region_code, obs_month, total_mortgages, mortgages_arrears,
            arrears_rate, printed_rate
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        list(payload.itertuples(index=False, name=None)),
    )


def load_macro(conn: sqlite3.Connection, df: pd.DataFrame) -> None:
    payload = df[["series_code", "series_label", "obs_date", "value"]].where(
        pd.notnull(df[["series_code", "series_label", "obs_date", "value"]]), None
    )
    conn.executemany(
        """
        INSERT INTO macro (series_code, series_label, obs_date, value)
        VALUES (?, ?, ?, ?)
        """,
        list(payload.itertuples(index=False, name=None)),
    )


def load_labour(conn: sqlite3.Connection, df: pd.DataFrame) -> None:
    payload = df[["region_code", "obs_month", "unemployment_rate"]].where(
        pd.notnull(df[["region_code", "obs_month", "unemployment_rate"]]), None
    )
    conn.executemany(
        """
        INSERT INTO labour (region_code, obs_month, unemployment_rate)
        VALUES (?, ?, ?)
        """,
        list(payload.itertuples(index=False, name=None)),
    )


def build_database(
    db_path: Path | None = None,
    pdf_path: Path | None = None,
    include_macro_labour: bool = True,
) -> Path:
    """Rebuild arrears.db from schema + CBA PDF (+ macro/labour when available)."""
    dest = db_path or DB_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()

    path = Path(pdf_path) if pdf_path else (cached_pdf_path() or download_latest())
    arrears_df = load_arrears_frame(path)

    conn = sqlite3.connect(dest)
    try:
        create_schema(conn)
        load_regions(conn)
        load_arrears(conn, arrears_df)
        load_breaks(conn)
        if include_macro_labour:
            ensure_statcan_zip()
            load_macro(conn, load_macro_long())
            load_labour(conn, build_labour_panel())
        conn.commit()
    finally:
        conn.close()
    return dest


def row_counts(db_path: Path | None = None) -> pd.DataFrame:
    dest = db_path or DB_PATH
    conn = sqlite3.connect(dest)
    try:
        return pd.read_sql_query(
            """
            SELECT region_code, COUNT(*) AS n_rows
            FROM arrears
            GROUP BY region_code
            ORDER BY region_code
            """,
            conn,
        )
    finally:
        conn.close()


def run_panel(db_path: Path | None = None) -> pd.DataFrame:
    dest = db_path or DB_PATH
    sql = PANEL_SQL_PATH.read_text()
    conn = sqlite3.connect(dest)
    try:
        return pd.read_sql_query(sql, conn)
    finally:
        conn.close()


def null_counts_by_decade(panel: pd.DataFrame) -> pd.DataFrame:
    df = panel.copy()
    df["decade"] = df["obs_month"].str.slice(0, 3) + "0s"
    cols = ["arrears_rate", "unemployment_rate", "policy_rate", "five_year_yield"]
    rows = []
    for decade, group in df.groupby("decade"):
        row = {"decade": decade, "n": len(group)}
        for col in cols:
            row[f"{col}_nulls"] = int(group[col].isna().sum())
        rows.append(row)
    return pd.DataFrame(rows).sort_values("decade")


def main() -> None:
    pdf = cached_pdf_path() or download_latest()
    db = build_database(pdf_path=pdf)
    counts = row_counts(db)
    print(f"db={db}")
    print(f"pdf={pdf.name}")
    print(f"report_month={report_month(load_arrears_frame(pdf))}")
    print(counts.to_string(index=False))

    panel = run_panel(db)
    print("\npanel first 20 rows:")
    print(panel.head(20).to_string(index=False))
    print("\nnull counts by decade:")
    print(null_counts_by_decade(panel).to_string(index=False))


if __name__ == "__main__":
    main()
