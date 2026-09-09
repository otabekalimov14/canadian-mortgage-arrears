# Canadian Mortgage Arrears: Macro Drivers by Province

Analysis project. Build a clean provincial panel of Canadian mortgage arrears going back to 1995, join it to macro data, and measure which variables lead arrears and by how many months.

This file is the source of truth for the agent. Read it fully before writing code.

---

## 1. Context

The Canadian Bankers Association publishes monthly counts of residential mortgages 90+ days past due, broken out by province, back to January 1995. The national arrears rate bottomed at 0.14% in 2022 and has roughly doubled since. The provincial spread is wide and the ranking has shifted: Saskatchewan has historically run highest, but Ontario has climbed sharply since 2023 after sitting near the bottom for a decade.

Bank of Canada research points to the labour market as the primary driver of arrears. This project tests that on the provincial panel and measures the lag.

The output is an analysis, not a model in production. Nobody is deploying this. The deliverable is a defensible answer to three questions plus the clean dataset that supports it.

## 2. Research questions

1. What is the lead time between a change in provincial unemployment and a change in that province's arrears rate?
2. Does the lead time differ by province, and if so, which provinces respond fastest?
3. Is the recent post-trough episode behaving like the 2008 to 2010 episode, or differently?

Answer each in one or two sentences backed by a number and a chart. If the data does not support a clean answer, say so. A null result stated clearly is a valid deliverable.

## 3. Data sources

### 3.1 CBA mortgage arrears (primary)

- URL pattern: `https://cba.ca/Assets/CanadianBankersAssociation/Documents/Articles/Statistics/stat-mortgages-arrears-{month}-{year}-en.pdf`
- Example that is confirmed to work: `stat-mortgages-arrears-march-2025-en.pdf`
- Find the current file from the CBA statistics page rather than guessing the month. Download the most recent one available.

**One PDF contains the entire history.** Do not scrape a file per month. A single download gives every region from 1995-01 to the report date. Golden checks in section 5 use March 2025 observations that must still be present in any newer full-history PDF.

Structure of the file:

- Page 1: summary table of the latest month, all regions
- Then one section per region: CANADA, ATLANTIC, QUEBEC, ONTARIO, MANITOBA, SASKATCHEWAN, ALBERTA, BRITISH COLUMBIA, TERRITORIES
- Each region section has three columns per observation: total number of mortgages, number in arrears, arrears as a percent of total

Region codes (use these everywhere):

| region_code | region_name         | notes |
|---|---|---|
| CAN | Canada | national total |
| ATL | Atlantic | NL + PE + NS + NB; no provincial split |
| QC | Quebec | |
| ON | Ontario | |
| MB | Manitoba | |
| SK | Saskatchewan | |
| AB | Alberta | CBA folds NWT and Nunavut into Alberta |
| BC | British Columbia | CBA folds Yukon into British Columbia |
| TERR | Territories | separate CBA section; often suppressed (asterisks) |

Do not reallocate mortgages across AB, BC, and TERR. Parse each section as printed.

### 3.2 Bank of Canada Valet API (macro)

- Base: `https://www.bankofcanada.ca/valet`
- No API key, no registration, no cost
- Discover series codes by calling the lists endpoint (`/lists/series/json`) and searching the labels. Do not hardcode a series code you have not verified returns the series you think it does. Print the series label alongside the first few observations and confirm before building on it.

Series to pull and store in `macro`:

- Target for the overnight rate (policy rate)
- Government of Canada 5 year benchmark bond yield (proxy for fixed mortgage pricing)
- Chartered bank prime rate
- Total CPI, year over year

**Frequency:** Valet observations may be daily. For the monthly analysis panel, take the last available observation in each calendar month. Store the full native-frequency series in `macro`; downsample only in SQL or analysis code.

**Scope:** Prime and CPI are stored for completeness and optional charts. Phases 2–5 acceptance only requires policy rate and 5-year yield on the joined panel.

### 3.3 Statistics Canada (labour)

- Table 14-10-0287-01, labour force characteristics, monthly, seasonally adjusted, by province
- Place the full CSV in `data/raw/` (download once from the table page; the loader reads the cached file and does not call the StatCan API)
- Filter to unemployment rate, both sexes, 15 years and over
- Also keep labour force size for the four Atlantic provinces so the ATL rate can be weighted

Map provinces to CBA regions: Atlantic is NL, PE, NS and NB combined — build the Atlantic unemployment rate as a labour-force-weighted average of those four. Do not use a simple mean.

**Territories labour:** Do not invent a TERR unemployment rate. Leave `labour` null for TERR. Exclude TERR from lag and regression samples that need unemployment. Nulls for TERR unemployment are expected; nulls for CAN/ATL/QC/ON/MB/SK/AB/BC unemployment after 1995 are not.

### 3.4 Optional, only if phases 1 to 4 are done

House price index by province, from CREA or StatCan Table 18-10-0205-01.

---

## 4. Data traps

These are real and will silently corrupt the dataset if ignored. Each one needs a test.

**Two column layout.** Every region section is printed as two side by side blocks. The left block runs 1995-01 to 2010-12. The right block runs 2011-01 to the present. A single line of extracted text therefore contains two unrelated observations, one from the 1990s or 2000s and one from the 2010s or 2020s. Parse using word x-coordinates (pdfplumber `extract_words`) or split each line into two halves on the second date pattern. If you concatenate lines naively you will produce a time series that jumps between decades and looks plausible.

**Region headers drift.** In extracted text the region label sometimes appears in the middle of a section rather than at the top. Do not assume the header is the first line of the block. Anchor on the label wherever it appears and assign it to the whole section.

**Suppressed values.** The Territories section has asterisks in the arrears and rate columns instead of numbers. Parse those to null, not to zero.

**Trailing blanks.** The right column is pre-printed with future months that have no values yet. Drop any row where the total is missing.

**Rounded percentages.** The printed rate column is rounded to two decimals, which throws away most of the signal at these levels. The difference between 0.195% and 0.204% both print as 0.20%. Recompute the rate as arrears divided by total and keep full precision. Use the printed column only as a validation check.

**Structural breaks in coverage.** The reporting panel is not constant. Manulife Bank joins in April 2004, Laurentian Bank in October 2010, Equitable Bank in November 2020. Quebec's total mortgage count jumps roughly 12% in October 2010 when Laurentian is added. There is also a documented reporting adjustment to Manitoba and Saskatchewan figures at 2006-11.

Record every one of these dates in the `breaks` table (that is how affected periods are marked — join to `breaks` in analysis, do not add a flag column on `arrears`). Do not silently smooth them. The count series is discontinuous across them. The rate series is less affected but not immune.

**Thousands separators and percent signs.** Numbers come out as `4,983,931` and `0.22%`. Strip before casting.

---

## 5. Validation gates

Do not proceed past parsing until all of these pass. Write them as tests, not as print statements.

Golden values from the March 2025 file (must match even if a newer PDF was downloaded):

| Region | Month | Total | Arrears | Rate |
|---|---|---|---|---|
| Canada | 2025-03 | 4,983,931 | 11,003 | 0.22% |
| Ontario | 2025-03 | 2,184,633 | 4,367 | 0.20% |
| Saskatchewan | 2025-03 | 123,523 | 672 | 0.54% |
| Quebec | 2025-03 | 930,998 | 1,697 | 0.18% |
| Canada | 1995-01 | 2,184,443 | 11,014 | 0.50% |

Structural checks:

- Every region has a continuous monthly series with no gaps and no duplicate months from 1995-01 through the report month, except that TERR may have null arrears/rate when suppressed
- Canada reconciliation: let S be the sum of `total_mortgages` over ATL, QC, ON, MB, SK, AB, BC, and TERR, treating a null TERR total as 0 for this check only. The source PDF itself is not perfectly additive in every month (verified against raw tokens, especially in the 1990s). Require: (a) no month has |S − Canada| / Canada above 3%; (b) at least 99% of months reconcile within 0.3%. A two-column mix-up would blow past both gates
- Every non-null computed rate falls between 0.0005 and 0.02 (raise if a real printed point falls outside — do not edit the test to hide a bad parse)
- Printed vs computed: at least 99% of rows with both rates present have absolute gap under 0.0001. Occasional source typos (printed percent inconsistent with the printed counts) are allowed
- Row count per region matches the number of months between 1995-01 and the report month (rows may exist with null arrears for suppressed TERR cells)

If goldens fail or the 3% / 99%-within-0.3% reconciliation gates fail, the parse is wrong. Fix the parser before continuing.

---

## 6. Schema

SQLite only. Do not also build Postgres/Supabase.

```sql
CREATE TABLE region (
    region_code   TEXT PRIMARY KEY,   -- 'ON', 'QC', 'ATL', 'CAN', ...
    region_name   TEXT NOT NULL,
    is_national   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE arrears (
    region_code      TEXT NOT NULL REFERENCES region(region_code),
    obs_month        TEXT NOT NULL,          -- 'YYYY-MM-01'
    total_mortgages  INTEGER,
    mortgages_arrears INTEGER,
    arrears_rate     REAL,                   -- recomputed, full precision
    printed_rate     REAL,                   -- as shown in the PDF, for validation
    PRIMARY KEY (region_code, obs_month)
);

CREATE TABLE macro (
    series_code TEXT NOT NULL,
    series_label TEXT NOT NULL,
    obs_date    TEXT NOT NULL,
    value       REAL,
    PRIMARY KEY (series_code, obs_date)
);

CREATE TABLE labour (
    region_code       TEXT NOT NULL REFERENCES region(region_code),
    obs_month         TEXT NOT NULL,
    unemployment_rate REAL,
    PRIMARY KEY (region_code, obs_month)
);

CREATE TABLE breaks (
    region_code TEXT,
    obs_month   TEXT NOT NULL,
    reason      TEXT NOT NULL
);
```

Macro is long format on purpose. New series drop in without a migration.

---

## 7. Repo structure

```
canadian-mortgage-arrears/
  README.md
  PROJECT_BRIEF.md
  AGENTS.md
  requirements.txt
  .gitignore              # data/raw contents, *.db, *.csv
  data/
    raw/                  # downloaded PDFs and CSVs, gitignored
    arrears.db            # gitignored
  sql/
    schema.sql
    01_panel.sql          # joined analysis view
    02_lag_table.sql
  src/
    fetch_cba.py
    parse_cba.py
    fetch_boc.py
    load_statcan.py
    build_db.py
  tests/
    test_parse.py         # golden values and structural checks
  notebooks/
    01-explore.ipynb
    02-lags.ipynb
    03-episodes.ipynb
  reports/
    figures/
```

---

## 8. Phases

Complete each phase and pass its acceptance test before starting the next. Do not work ahead.

### Phase 1: Ingest and parse

Download the latest CBA PDF. Parse all nine regions into a tidy dataframe. Write the schema and load it.

Acceptance: every check in section 5 passes as an automated test.

### Phase 2: Macro and labour

Pull the Valet series. Load the StatCan unemployment CSV. Build the weighted Atlantic unemployment rate. Load both into the database.

Acceptance: a single SQL query returns a joined monthly panel of region, arrears rate, unemployment rate, policy rate and 5 year yield, with no unexpected nulls after 1995 (see section 3.3 for which nulls are expected).

### Phase 3: Lag analysis

For each province with unemployment data (exclude TERR; exclude CAN unless used as a reference row), compute the cross correlation between month-over-month change in unemployment and month-over-month change in arrears rate, at lags 0 through 24 months. Do the same for the policy rate and the 5 year yield (national drivers, still estimated per province).

**Peak lag rule:** choose the lag that maximises the absolute correlation; report that lag and the signed correlation. First differences are used so a shared trend does not dominate the correlation.

Acceptance: a table of provinces by driver showing peak lag and correlation, plus one chart of the correlation profile for Ontario and one for Saskatchewan.

### Phase 4: Panel regression

Regress arrears rate (level) on lagged unemployment, lagged policy rate, and province fixed effects.

**Lag lengths:** Phase 3 produces a different peak lag per province. For the panel, use one lag per driver: the median across provinces of that driver’s peak lag (unemployment median for the unemployment lag; policy-rate median for the policy lag). State those two integers in the write-up. Do not put the 5-year yield in the baseline regression (keep the specification small); it remains in the Phase 3 table.

Report coefficients with heteroskedasticity-robust standard errors in a readable table, not raw statsmodels output. Clustering by province is not required (too few provinces); mention that as a limitation.

State plainly what the coefficient means in words. "A one percentage point rise in provincial unemployment is associated with an X basis point rise in the arrears rate N months later."

Acceptance: one table, one paragraph of interpretation.

### Phase 5: Episode comparison

Define troughs from the **national (CAN) arrears rate**: the minimum in 2007-01 to 2010-12 (GFC window) and the minimum in 2021-01 through the latest month (recent window). Align both episodes at month 0 = trough. Plot each province’s arrears rate relative to its own level at that trough, for months 0 through 24 (or through end of sample if shorter).

**Faster/slower rule:** compare the change in the national arrears rate from trough to trough+18 months (or latest month if fewer than 18). Supplement with a visual read of provincial paths.

Acceptance: one chart, one paragraph on whether the current cycle is faster, slower or similar, and one sentence on what is different about the composition of the panel between the two periods (see the coverage breaks in section 4).

### Phase 6: Write up

README with the three questions, the answers, four charts, the data traps you handled, and the limitations. Limitations must include the changing bank panel, the aggregation of Atlantic and the territories, and the fact that arrears at 90 days is a lagging indicator that misses borrowers who were offered amortization extensions instead of going delinquent.

---

## 9. Constraints

- Python 3.11+, pandas, pdfplumber, requests, statsmodels, matplotlib, SQLite. pytest is allowed for tests. Ask before adding anything else.
- No machine learning. This is an econometrics problem, not a prediction problem.
- No dashboard, no Streamlit, no Docker, no FastAPI.
- Do not commit PDFs, CSVs or the database. Gitignore them and document how to fetch.
- Every function that touches parsed data gets a test.
- Cache downloads to `data/raw/` and do not refetch on every run.
- If a number in the analysis cannot be traced back to a source row, it does not go in the README.

## 10. Explanation requirement

The owner of this repo needs to defend every decision in an interview. At the end of each phase, output a short plain-language summary covering:

- What you built
- Any statistical choice you made and why, in one sentence each
- Anything you were uncertain about
- What a reviewer would most likely challenge

No jargon in that summary. If the explanation needs a glossary, the choice was too complicated for the phase.

## 11. Locked decisions

These close ambiguities so the agent does not invent silent defaults later. Defend them in interviews as deliberate choices.

1. **Repo name / rules file:** Project root is `canadian-mortgage-arrears`. Agent rules live in `AGENTS.md`.
2. **SQLite only.** No Supabase/Postgres dual stack.
3. **Territories:** Parse TERR as its own region. AB/BC folding is CBA’s geography note, not a reason to move rows. No TERR unemployment series.
4. **Canada reconciliation:** Sum of eight sub-national totals vs CAN; null TERR total counts as 0 for that sum only. Gate is 99% of months within 0.3% and no month above 3% — the source PDF is not perfectly additive, especially early on.
5. **Macro calendar:** Last observation in each calendar month for monthly joins; prime and CPI stored but not required in the core panel.
6. **StatCan:** Human (or one-off browser) download into `data/raw/`; `load_statcan.py` reads the cache only.
7. **Breaks:** Rows in `breaks` are the mark; join when analysing.
8. **Peak correlation:** Argmax of absolute correlation; report signed value.
9. **Panel lags:** Median across provinces of Phase 3 peak lags, one per driver; unemployment + policy rate + province FE; robust (not clustered) SEs.
10. **Episodes:** National arrears troughs in the GFC and 2021–present windows; speed = CAN rate change trough to trough+18.
