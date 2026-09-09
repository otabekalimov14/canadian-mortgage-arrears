"""Download the latest CBA residential mortgage arrears PDF into data/raw/."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import requests

BASE_URL = (
    "https://cba.ca/Assets/CanadianBankersAssociation/Documents/"
    "Articles/Statistics/stat-mortgages-arrears-{month}-{year}-en.pdf"
)
MONTHS = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]
RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
FILENAME_RE = re.compile(
    r"stat-mortgages-arrears-(?P<month>[a-z]+)-(?P<year>\d{4})-en\.pdf$",
    re.IGNORECASE,
)


def report_month_from_filename(filename: str) -> str:
    """Return 'YYYY-MM-01' for a CBA arrears PDF filename."""
    match = FILENAME_RE.search(filename)
    if not match:
        raise ValueError(f"Unrecognised CBA filename: {filename}")
    month_name = match.group("month").lower()
    year = int(match.group("year"))
    month_num = MONTHS.index(month_name) + 1
    return f"{year:04d}-{month_num:02d}-01"


def candidate_urls(start: date | None = None, months_back: int = 24) -> list[tuple[str, str]]:
    """Yield (filename, url) pairs from start month backwards."""
    cursor = start or date.today().replace(day=1)
    out: list[tuple[str, str]] = []
    year, month = cursor.year, cursor.month
    for _ in range(months_back):
        name = MONTHS[month - 1]
        filename = f"stat-mortgages-arrears-{name}-{year}-en.pdf"
        url = BASE_URL.format(month=name, year=year)
        out.append((filename, url))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return out


def find_latest_pdf(
    session: requests.Session | None = None,
    months_back: int = 24,
) -> tuple[str, str]:
    """
    Probe the known CBA URL pattern until a PDF responds 200.

    Returns (filename, url). Raises FileNotFoundError if none found.
    """
    sess = session or requests.Session()
    sess.headers.setdefault(
        "User-Agent",
        "canadian-mortgage-arrears/0.1 (portfolio research; python-requests)",
    )
    for filename, url in candidate_urls(months_back=months_back):
        response = sess.head(url, allow_redirects=True, timeout=30)
        # Some hosts reject HEAD; fall back to a ranged GET.
        if response.status_code == 405 or response.status_code >= 400:
            response = sess.get(url, stream=True, timeout=30)
            response.close()
        if response.status_code == 200:
            return filename, url
    raise FileNotFoundError(
        f"No CBA arrears PDF found in the last {months_back} months"
    )


def cached_pdf_path(raw_dir: Path | None = None) -> Path | None:
    """Return the newest cached CBA arrears PDF in raw_dir, if any."""
    directory = raw_dir or RAW_DIR
    matches = sorted(directory.glob("stat-mortgages-arrears-*-en.pdf"))
    if not matches:
        return None
    # Prefer by report month encoded in the name, not mtime.
    return max(matches, key=lambda p: report_month_from_filename(p.name))


def download_latest(
    raw_dir: Path | None = None,
    force: bool = False,
    months_back: int = 24,
) -> Path:
    """
    Ensure the latest CBA arrears PDF is in raw_dir.

    Skips the network download when a cached file already matches the
    newest filename found on the server (or when force is False and any
    cache exists and still is the latest probed name).
    """
    directory = raw_dir or RAW_DIR
    directory.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    filename, url = find_latest_pdf(session=session, months_back=months_back)
    dest = directory / filename

    if dest.exists() and not force:
        return dest

    # If an older cache exists but a newer month is available, download the new one.
    response = session.get(url, timeout=120)
    response.raise_for_status()
    dest.write_bytes(response.content)
    return dest


def main() -> None:
    path = download_latest()
    report_month = report_month_from_filename(path.name)
    print(f"file={path.name}")
    print(f"report_month={report_month}")
    print(f"path={path}")


if __name__ == "__main__":
    main()
