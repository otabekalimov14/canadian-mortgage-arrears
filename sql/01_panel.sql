-- Monthly analysis panel: arrears, unemployment, policy rate, and 5-year yield by region.

WITH policy_monthly AS (
    SELECT
        series_code,
        printf('%04d-%02d-01',
               CAST(substr(obs_date, 1, 4) AS INTEGER),
               CAST(substr(obs_date, 6, 2) AS INTEGER)
        ) AS obs_month,
        value AS policy_rate,
        ROW_NUMBER() OVER (
            PARTITION BY series_code,
                         printf('%04d-%02d-01',
                                CAST(substr(obs_date, 1, 4) AS INTEGER),
                                CAST(substr(obs_date, 6, 2) AS INTEGER)
                         )
            ORDER BY obs_date DESC
        ) AS rn
    FROM macro
    WHERE series_code = 'STATIC_ATABLE_V39079'
),
yield_monthly AS (
    SELECT
        series_code,
        printf('%04d-%02d-01',
               CAST(substr(obs_date, 1, 4) AS INTEGER),
               CAST(substr(obs_date, 6, 2) AS INTEGER)
        ) AS obs_month,
        value AS five_year_yield,
        ROW_NUMBER() OVER (
            PARTITION BY series_code,
                         printf('%04d-%02d-01',
                                CAST(substr(obs_date, 1, 4) AS INTEGER),
                                CAST(substr(obs_date, 6, 2) AS INTEGER)
                         )
            ORDER BY obs_date DESC
        ) AS rn
    FROM macro
    WHERE series_code = 'BD.CDN.5YR.DQ.YLD'
),
policy AS (
    SELECT obs_month, policy_rate
    FROM policy_monthly
    WHERE rn = 1
),
five_year AS (
    SELECT obs_month, five_year_yield
    FROM yield_monthly
    WHERE rn = 1
)
SELECT
    a.region_code,
    a.obs_month,
    a.arrears_rate,
    l.unemployment_rate,
    p.policy_rate,
    y.five_year_yield
FROM arrears AS a
LEFT JOIN labour AS l
    ON l.region_code = a.region_code
   AND l.obs_month = a.obs_month
LEFT JOIN policy AS p
    ON p.obs_month = a.obs_month
LEFT JOIN five_year AS y
    ON y.obs_month = a.obs_month
WHERE a.region_code != 'TERR'
ORDER BY a.region_code, a.obs_month;
