# Canadian Mortgage Arrears: Macro Drivers by Province

Provincial panel of CBA residential mortgages 90+ days past due (1995–present), joined later to Bank of Canada rates and StatCan unemployment, to measure how long labour-market and rate moves lead arrears.

**Spec:** [PROJECT_BRIEF.md](PROJECT_BRIEF.md) · **Agent rules:** [AGENTS.md](AGENTS.md)

Findings and charts go in this README after Phase 6. Until then, work one phase at a time.

---

## Setup

Python 3.11+:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Phase 1 status (done)

Ingest and parse the CBA arrears PDF; load SQLite.

| Step | Command |
|---|---|
| Download / cache latest PDF | `python src/fetch_cba.py` |
| Parse (smoke) | `python src/parse_cba.py` |
| Tests (section 5 gates) | `python -m pytest tests/test_parse.py -v` |
| Build DB | `python src/build_db.py` |

Artifacts (gitignored): `data/raw/stat-mortgages-arrears-*-en.pdf`, `data/arrears.db`.

### What Phase 1 produced

- Nine regions (`CAN`, `ATL`, `QC`, `ON`, `MB`, `SK`, `AB`, `BC`, `TERR`), monthly from 1995-01 through the report month
- `arrears_rate` recomputed as arrears ÷ total (full precision); `printed_rate` kept for checks
- `breaks` table for bank-panel joins and the 2006-11 MB/SK reporting adjustment

### Data traps handled

- **Two-column PDF layout** — left block ~1995–2010, right block ~2011–present; parse by word x-coordinate, not left-to-right line text
- **Suppressed Territories** — `*` → null, not zero
- **Trailing blank months** — future dates with no totals are dropped
- **Split thousands** — pdfplumber sometimes splits `2,618` into `2` + `,618`; fragments are rejoined
- **Canada sum** — source PDF is not perfectly additive every month (checked against raw tokens). Tests require no gap above 3% and ≥99% of months within 0.3%

### Reproduce golden checks

March 2025 and January 1995 Canada / Ontario / Saskatchewan / Quebec counts in `tests/test_parse.py` must match even when a newer full-history PDF is cached.
