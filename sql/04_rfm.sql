-- RFM segmentation of customers (people, not order-level customer_ids).
-- Almost everyone buys once, so frequency is split into 1 vs 2+ instead of quintiles.

CREATE OR REPLACE TABLE mart_rfm AS
WITH valid AS (
    SELECT customer_unique_id, purchased_at, gmv
    FROM fct_orders
    WHERE order_status = 'delivered'
),
ref AS (
    SELECT MAX(purchased_at)::DATE + 1 AS ref_date FROM valid
),
per_customer AS (
    SELECT
        customer_unique_id,
        DATE_DIFF('day', MAX(purchased_at)::DATE, (SELECT ref_date FROM ref)) AS recency_days,
        COUNT(*)  AS frequency,
        SUM(gmv)  AS monetary
    FROM valid
    GROUP BY 1
),
scored AS (
    SELECT
        *,
        6 - NTILE(5) OVER (ORDER BY recency_days) AS r_score,   -- 5 = bought most recently
        NTILE(5) OVER (ORDER BY monetary)         AS m_score    -- 5 = spent the most
    FROM per_customer
)
SELECT
    *,
    CASE
        WHEN frequency >= 2 AND r_score >= 4 THEN 'Repeat, active'
        WHEN frequency >= 2                  THEN 'Repeat, drifting'
        WHEN r_score >= 4 AND m_score >= 4   THEN 'New, high spend'
        WHEN r_score >= 4                    THEN 'New'
        WHEN m_score >= 4                    THEN 'Lapsed, high spend'
        ELSE                                      'Lapsed'
    END AS segment
FROM scored;
