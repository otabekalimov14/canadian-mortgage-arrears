# Agent rules: canadian-mortgage-arrears

Read PROJECT_BRIEF.md before doing anything. It is the spec. Section 11 locks decisions that used to be ambiguous — follow those; do not reopen them silently.

## Working style

- Work one phase at a time. Do not start phase N+1 until phase N's acceptance test passes.
- Before writing code for a phase, state your plan in three or four bullets and wait for confirmation.
- Small commits with plain messages. One concern per commit. Only commit when the owner asks.
- If you hit something ambiguous that section 11 does not cover, ask. Do not pick a reasonable-seeming default and move on silently.

## Code

- Python 3.11+. Standard library plus pandas, pdfplumber, requests, statsmodels, matplotlib, sqlite3. pytest for tests.
- Ask before adding any dependency not in that list.
- Plain functions over classes. No abstract base classes, no plugin architecture, no config framework.
- Type hints on function signatures. Docstrings only where the function does something non-obvious.
- No bare except. Catch what you expect.
- Never use `sys.exit` or `os._exit` in library code.

## Data handling

- Never hardcode a parsed value to make a test pass.
- Never fill missing data with zero. Missing is null. (The Canada reconciliation check may treat a null TERR total as 0 for summing only — see PROJECT_BRIEF.md section 5.)
- Never smooth, interpolate or drop an outlier without saying so in the README.
- Cache every download to data/raw/. Check the cache before making a network request.
- Recompute rates from counts. Do not trust rounded percentages printed in the source.

## Testing

- Every parsing function has a test against the golden values in PROJECT_BRIEF.md section 5.
- Tests run with pytest and pass before any phase is considered complete.
- If a test fails, fix the code, not the test.

## SQL

- Analysis joins live in sql/ as readable .sql files, not buried in Python string literals.
- Use CTEs over nested subqueries.
- Every query file starts with a one-line comment saying what question it answers.

## Explaining

The repo owner is a first year student who will be asked about this in interviews. After each phase, write a short summary in plain language covering what you built, each statistical choice and why, what you were unsure about, and what a reviewer would challenge first.

Do not use jargon in that summary without defining it in the same sentence.

## Out of scope

Do not build any of these, even if they seem like an improvement:

- Machine learning models of any kind
- Dashboards, web apps, APIs
- Docker, CI pipelines, cloud deployment
- Automated monthly refresh jobs
- Additional datasets beyond those named in the brief
