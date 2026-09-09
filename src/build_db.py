"""Create SQLite DB, load regions / arrears / coverage breaks."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from fetch_cba import cached_pdf_path, download_latest
from parse_cba import load_arrears_frame, report_month

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "sql" / "schema.sql"
DB_PATH = ROOT / "data" / "arrears.db"

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


def build_database(
    db_path: Path | None = None,
    pdf_path: Path | None = None,
) -> Path:
    """Rebuild arrears.db from schema + parsed CBA PDF."""
    dest = db_path or DB_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()

    path = Path(pdf_path) if pdf_path else (cached_pdf_path() or download_latest())
    df = load_arrears_frame(path)

    conn = sqlite3.connect(dest)
    try:
        create_schema(conn)
        load_regions(conn)
        load_arrears(conn, df)
        load_breaks(conn)
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


def main() -> None:
    pdf = cached_pdf_path() or download_latest()
    db = build_database(pdf_path=pdf)
    counts = row_counts(db)
    print(f"db={db}")
    print(f"pdf={pdf.name}")
    print(f"report_month={report_month(load_arrears_frame(pdf))}")
    print(counts.to_string(index=False))


if __name__ == "__main__":
    main()
