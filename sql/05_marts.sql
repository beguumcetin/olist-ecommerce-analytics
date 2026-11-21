-- Summary tables for the dashboard. Each is small enough to export as CSV.

CREATE OR REPLACE TABLE mart_delivery_reviews AS
SELECT
    CASE
        WHEN delay_days <= -10 THEN '1. 10+ days early'
        WHEN delay_days <   0  THEN '2. 1-9 days early'
        WHEN delay_days =   0  THEN '3. On the promised day'
        WHEN delay_days <=  3  THEN '4. 1-3 days late'
        WHEN delay_days <=  7  THEN '5. 4-7 days late'
        ELSE                        '6. 8+ days late'
    END                                     AS delivery_bucket,
    COUNT(*)                                AS orders,
    AVG(review_score)                       AS avg_score,
    AVG((review_score <= 2)::INT)           AS low_score_share
FROM fct_orders
WHERE order_status = 'delivered' AND delivered_at IS NOT NULL AND review_score IS NOT NULL
GROUP BY 1
ORDER BY 1;

CREATE OR REPLACE TABLE mart_monthly AS
SELECT
    purchase_month,
    COUNT(*)                         AS orders,
    COUNT(DISTINCT customer_unique_id) AS customers,
    SUM(gmv)                         AS gmv,
    AVG(gmv)                         AS avg_order_value,
    AVG(is_late::INT)                AS late_share,
    AVG(review_score)                AS avg_score
FROM fct_orders
WHERE order_status NOT IN ('canceled', 'unavailable')
GROUP BY 1
ORDER BY 1;

CREATE OR REPLACE TABLE mart_states AS
SELECT
    customer_state,
    COUNT(*)                         AS orders,
    COUNT(DISTINCT customer_unique_id) AS customers,
    SUM(gmv)                         AS gmv,
    AVG(delivery_days)               AS avg_delivery_days,
    AVG(is_late::INT)                AS late_share,
    AVG(freight_share)               AS avg_freight_share,
    AVG(review_score)                AS avg_score
FROM fct_orders
WHERE order_status = 'delivered'
GROUP BY 1
ORDER BY orders DESC;

CREATE OR REPLACE TABLE mart_categories AS
SELECT
    main_category,
    COUNT(*)                         AS orders,
    SUM(gmv)                         AS gmv,
    AVG(gmv)                         AS avg_order_value,
    AVG(is_late::INT)                AS late_share,
    AVG(review_score)                AS avg_score
FROM fct_orders
WHERE order_status = 'delivered'
GROUP BY 1
ORDER BY gmv DESC;
