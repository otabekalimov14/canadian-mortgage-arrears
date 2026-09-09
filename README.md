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
| Build DB (Phase 1 only) | `python -c "from build_db import build_database; build_database(include_macro_labour=False)"` from `src/` |

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

## Phase 2 status (done)

Macro (Bank of Canada Valet) + labour (StatCan 14-10-0287-01) joined in `sql/01_panel.sql`.

| Step | Command |
|---|---|
| Confirm / peek Valet series | `python src/fetch_boc.py` |
| Cache StatCan ZIP | place `14100287-eng.zip` in `data/raw/` (from [StatCan CSV zip](https://www150.statcan.gc.ca/n1/tbl/csv/14100287-eng.zip)) |
| Rebuild full DB + print panel | `python src/build_db.py` |

### Valet series locked

| Role | Code | Starts |
|---|---|---|
| Overnight target (policy) | `STATIC_ATABLE_V39079` | 1996-01 |
| 5-year GoC benchmark yield | `BD.CDN.5YR.DQ.YLD` | 2001-01 |
| Prime | `V80691311` | 1975 |
| CPI YoY | `STATIC_TOTALCPICHANGE` | 1995-01 |

Daily series are stored at native frequency in `macro`; the panel uses the last observation in each calendar month.

### Expected panel nulls (not join bugs)

- `policy_rate`: null in 1995 (series starts 1996)
- `five_year_yield`: null before 2001
- `unemployment_rate`: null for `TERR` only (excluded from the panel query)
- Atlantic unemployment is labour-force-weighted across NL, PE, NS, NB

## Phase 3 status (done)

Lag analysis: cross-correlation of month-over-month changes at lags 0–24.

| Step | Command |
|---|---|
| Run peaks + charts | `python src/lags.py` |
| Notebook | `notebooks/02-lags.ipynb` |

Outputs: `reports/lag_peaks.csv`, `reports/figures/lag_profile_ON_unemployment.png`, `reports/figures/lag_profile_SK_unemployment.png`.

**Headline:** Ontario unemployment peak lag = **1 month**; Saskatchewan = **10 months**. ATL and BC peak at **0** (same month). Correlations are modest (~0.12–0.16 for unemployment).
