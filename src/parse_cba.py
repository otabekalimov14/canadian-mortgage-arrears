"""Parse CBA residential mortgage arrears PDFs into a tidy dataframe."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pdfplumber

from fetch_cba import cached_pdf_path, download_latest, report_month_from_filename

DATE_RE = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{2})$")
COLUMN_SPLIT_X = 310.0

REGION_NAME_TO_CODE = {
    "CANADA": "CAN",
    "ATLANTIC": "ATL",
    "QUEBEC": "QC",
    "ONTARIO": "ON",
    "MANITOBA": "MB",
    "SASKATCHEWAN": "SK",
    "ALBERTA": "AB",
    "BRITISH COLUMBIA": "BC",
    "TERRITORIES": "TERR",
}

REGION_CODES = list(REGION_NAME_TO_CODE.values())


def _clean_region_token(text: str) -> str:
    return text.replace("*", "").replace("(1)", "").replace("(2)", "").replace("(3)", "").strip()


def _parse_region_label(words: list[dict], region_idx: int) -> str | None:
    """Read REGION: <NAME> from word stream; name may span multiple tokens."""
    parts: list[str] = []
    for word in words[region_idx + 1 : region_idx + 4]:
        token = _clean_region_token(word["text"])
        if not token or token in {"(1)", "(2)", "(3)"}:
            break
        if token.startswith("Number") or token in {"DB50", "PUBLIC"}:
            break
        parts.append(token)
        joined = " ".join(parts)
        if joined in REGION_NAME_TO_CODE:
            return joined
        # Stop once we have a single-token match opportunity exhausted
        if len(parts) == 1 and joined not in {"BRITISH"}:
            if joined in REGION_NAME_TO_CODE:
                return joined
            # Unknown single token — keep going only for BRITISH COLUMBIA
            if joined != "BRITISH":
                break
    joined = " ".join(parts)
    return joined if joined in REGION_NAME_TO_CODE else None


def _to_int(token: str) -> int | None:
    if token == "*":
        return None
    return int(token.replace(",", ""))


def _to_rate(token: str) -> float | None:
    if token == "*":
        return None
    return float(token.replace("%", "")) / 100.0


def _merge_split_numbers(tokens: list[str]) -> list[str]:
    """
    Rejoin thousands that pdfplumber sometimes splits, e.g. '2' + ',618' -> '2,618'.
    """
    merged: list[str] = []
    i = 0
    while i < len(tokens):
        cur = tokens[i]
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        if nxt is not None:
            if re.fullmatch(r"\d{1,3}", cur) and re.fullmatch(r",\d{3}", nxt):
                merged.append(cur + nxt)
                i += 2
                continue
            if re.fullmatch(r"\d{1,3},", cur) and re.fullmatch(r"\d{3}", nxt):
                merged.append(cur + nxt)
                i += 2
                continue
        merged.append(cur)
        i += 1
    return merged


def _parse_block(tokens: list[str]) -> dict | None:
    """
    Parse one side of a two-column row.

    Expected: date [, total, arrears, rate]. Date-only rows are trailing blanks.
    """
    if not tokens:
        return None
    tokens = _merge_split_numbers(tokens)
    # Skip leading junk on the same baseline (e.g. a 'Public' watermark fragment).
    start = next((i for i, t in enumerate(tokens) if DATE_RE.match(t)), None)
    if start is None:
        return None
    tokens = tokens[start:]
    match = DATE_RE.match(tokens[0])
    assert match is not None
    obs_month = f"{match.group('year')}-{match.group('month')}-01"
    if len(tokens) == 1:
        return None  # printed future month with no values
    if len(tokens) < 4:
        # Incomplete non-blank row — treat as unusable trailing / partial
        return None
    total = _to_int(tokens[1])
    if total is None:
        # Missing total means drop the row (trailing blank variant)
        return None
    arrears = _to_int(tokens[2])
    printed_rate = _to_rate(tokens[3])
    return {
        "obs_month": obs_month,
        "total_mortgages": total,
        "mortgages_arrears": arrears,
        "printed_rate": printed_rate,
    }


def _group_words_by_row(words: list[dict], y_tol: float = 2.0) -> list[list[dict]]:
    """Cluster words that share a vertical position into left-to-right rows."""
    if not words:
        return []
    ordered = sorted(words, key=lambda w: (w["top"], w["x0"]))
    rows: list[list[dict]] = []
    current: list[dict] = [ordered[0]]
    current_top = ordered[0]["top"]
    for word in ordered[1:]:
        if abs(word["top"] - current_top) <= y_tol:
            current.append(word)
        else:
            rows.append(sorted(current, key=lambda w: w["x0"]))
            current = [word]
            current_top = word["top"]
    rows.append(sorted(current, key=lambda w: w["x0"]))
    return rows


def _rows_from_page(words: list[dict]) -> list[dict]:
    """Extract observation dicts from one PDF page's words."""
    observations: list[dict] = []
    for row in _group_words_by_row(words):
        left_tokens = [w["text"] for w in row if w["x0"] < COLUMN_SPLIT_X]
        right_tokens = [w["text"] for w in row if w["x0"] >= COLUMN_SPLIT_X]
        for tokens in (left_tokens, right_tokens):
            parsed = _parse_block(tokens)
            if parsed is not None:
                observations.append(parsed)
    return observations


def parse_pdf(pdf_path: Path | str) -> pd.DataFrame:
    """
    Parse all nine CBA regions from one arrears PDF.

    Returns columns: region_code, obs_month, total_mortgages,
    mortgages_arrears, printed_rate.
    """
    path = Path(pdf_path)
    records: list[dict] = []
    current_code: str | None = None

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False)
            # Region header can appear mid-block; scan whole page.
            for idx, word in enumerate(words):
                if word["text"] != "REGION:":
                    continue
                label = _parse_region_label(words, idx)
                if label is None:
                    raise ValueError(
                        f"Unrecognised region label after REGION: near top={word['top']}"
                    )
                current_code = REGION_NAME_TO_CODE[label]

            if current_code is None:
                continue

            for obs in _rows_from_page(words):
                records.append({"region_code": current_code, **obs})

    if not records:
        raise ValueError(f"No arrears rows parsed from {path}")

    df = pd.DataFrame.from_records(records)
    df = df.drop_duplicates(subset=["region_code", "obs_month"], keep="first")
    df = df.sort_values(["region_code", "obs_month"]).reset_index(drop=True)
    return df


def add_computed_rate(df: pd.DataFrame) -> pd.DataFrame:
    """Add full-precision arrears_rate = arrears / total when both present."""
    out = df.copy()
    arrears = out["mortgages_arrears"]
    total = out["total_mortgages"]
    out["arrears_rate"] = arrears / total
    out.loc[arrears.isna() | total.isna() | (total == 0), "arrears_rate"] = pd.NA
    return out


def report_month(df: pd.DataFrame) -> str:
    """Latest month with a Canada total present."""
    can = df.loc[df["region_code"] == "CAN"].dropna(subset=["total_mortgages"])
    if can.empty:
        raise ValueError("No Canada rows with totals")
    return str(can["obs_month"].max())


def load_arrears_frame(pdf_path: Path | str | None = None) -> pd.DataFrame:
    """Download/cache if needed, parse, and attach computed rates."""
    path = Path(pdf_path) if pdf_path else download_latest()
    parsed = parse_pdf(path)
    return add_computed_rate(parsed)


def main() -> None:
    path = cached_pdf_path() or download_latest()
    df = load_arrears_frame(path)
    print(f"pdf={path.name}")
    print(f"filename_report_month={report_month_from_filename(path.name)}")
    print(f"data_report_month={report_month(df)}")
    print(f"rows={len(df)}")
    print(df.groupby("region_code").size().to_string())


if __name__ == "__main__":
    main()
