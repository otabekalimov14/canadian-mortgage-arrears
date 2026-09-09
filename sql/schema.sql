-- Schema for the Canadian mortgage arrears provincial panel (see PROJECT_BRIEF.md section 6).

CREATE TABLE region (
    region_code   TEXT PRIMARY KEY,
    region_name   TEXT NOT NULL,
    is_national   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE arrears (
    region_code       TEXT NOT NULL REFERENCES region(region_code),
    obs_month         TEXT NOT NULL,
    total_mortgages   INTEGER,
    mortgages_arrears INTEGER,
    arrears_rate      REAL,
    printed_rate      REAL,
    PRIMARY KEY (region_code, obs_month)
);

CREATE TABLE macro (
    series_code  TEXT NOT NULL,
    series_label TEXT NOT NULL,
    obs_date     TEXT NOT NULL,
    value        REAL,
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
