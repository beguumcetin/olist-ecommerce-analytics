-- Monthly acquisition cohorts: of the people who first bought in month M,
-- what share bought again k months later?

CREATE OR REPLACE TABLE mart_cohorts AS
WITH valid AS (
    SELECT customer_unique_id, purchase_month
    FROM fct_orders
    WHERE order_status NOT IN ('canceled', 'unavailable')
      AND purchase_month <= DATE '2018-08-01'  -- the data thins out after August 2018
),
first_purchase AS (
    SELECT customer_unique_id, MIN(purchase_month) AS cohort_month
    FROM valid
    GROUP BY 1
),
activity AS (
    SELECT DISTINCT
        v.customer_unique_id,
        f.cohort_month,
        DATE_DIFF('month', f.cohort_month, v.purchase_month) AS month_offset
    FROM valid v
    JOIN first_purchase f USING (customer_unique_id)
)
SELECT
    cohort_month,
    month_offset,
    COUNT(*) AS customers,
    COUNT(*)::DOUBLE / FIRST_VALUE(COUNT(*)) OVER (
        PARTITION BY cohort_month ORDER BY month_offset
    ) AS retention
FROM activity
GROUP BY 1, 2
ORDER BY 1, 2;
