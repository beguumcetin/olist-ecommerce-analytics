-- Typed, one-row-per-key views over the raw Olist tables.
-- Everything downstream reads these, never the raw_* tables.

CREATE OR REPLACE VIEW stg_orders AS
SELECT
    order_id,
    customer_id,
    order_status,
    TRY_CAST(order_purchase_timestamp AS TIMESTAMP)      AS purchased_at,
    TRY_CAST(order_delivered_customer_date AS TIMESTAMP) AS delivered_at,
    TRY_CAST(order_estimated_delivery_date AS TIMESTAMP) AS estimated_at
FROM raw_orders;

-- customer_id is per order; customer_unique_id is the actual person.
CREATE OR REPLACE VIEW stg_customers AS
SELECT customer_id, customer_unique_id, customer_state, customer_city
FROM raw_customers;

CREATE OR REPLACE VIEW stg_products AS
SELECT
    p.product_id,
    COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS category
FROM raw_products p
LEFT JOIN raw_category_translation t USING (product_category_name);

-- A few orders have more than one review; keep the latest.
CREATE OR REPLACE VIEW stg_reviews AS
SELECT order_id, review_score
FROM raw_order_reviews
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY order_id ORDER BY TRY_CAST(review_creation_date AS TIMESTAMP) DESC
) = 1;

CREATE OR REPLACE VIEW stg_payments AS
SELECT
    order_id,
    SUM(payment_value)                    AS paid,
    MAX(payment_installments)             AS installments,
    ARG_MAX(payment_type, payment_value)  AS main_payment_type
FROM raw_order_payments
GROUP BY order_id;
