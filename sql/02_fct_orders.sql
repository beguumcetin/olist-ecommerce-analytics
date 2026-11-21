-- One row per order with everything the analyses need.

CREATE OR REPLACE TABLE fct_orders AS
WITH items AS (
    SELECT
        i.order_id,
        COUNT(*)                        AS n_items,
        SUM(i.price)                    AS items_value,
        SUM(i.freight_value)            AS freight_value,
        COUNT(DISTINCT i.seller_id)     AS n_sellers,
        ARG_MAX(p.category, i.price)    AS main_category,   -- category of the priciest item
        LIST(DISTINCT s.seller_state)   AS seller_states
    FROM raw_order_items i
    LEFT JOIN stg_products p USING (product_id)
    LEFT JOIN raw_sellers  s USING (seller_id)
    GROUP BY i.order_id
)
SELECT
    o.order_id,
    c.customer_unique_id,
    c.customer_state,
    o.order_status,
    o.purchased_at,
    DATE_TRUNC('month', o.purchased_at)::DATE                        AS purchase_month,
    o.delivered_at,
    o.estimated_at,
    (EPOCH(o.delivered_at) - EPOCH(o.purchased_at)) / 86400.0        AS delivery_days,
    -- Positive = arrived after the date promised at checkout.
    DATE_DIFF('day', o.estimated_at::DATE, o.delivered_at::DATE)     AS delay_days,
    o.delivered_at::DATE > o.estimated_at::DATE                      AS is_late,
    i.n_items,
    i.n_sellers,
    i.items_value,
    i.freight_value,
    i.items_value + i.freight_value                                  AS gmv,
    i.freight_value / NULLIF(i.items_value + i.freight_value, 0)     AS freight_share,
    i.main_category,
    LEN(i.seller_states) = 1 AND i.seller_states[1] = c.customer_state AS same_state,
    pay.main_payment_type,
    pay.installments,
    r.review_score
FROM stg_orders o
JOIN items i              USING (order_id)
JOIN stg_customers c      USING (customer_id)
LEFT JOIN stg_payments pay USING (order_id)
LEFT JOIN stg_reviews r    USING (order_id);
