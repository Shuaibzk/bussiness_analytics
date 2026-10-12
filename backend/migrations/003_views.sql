-- 003: the flat read model.  The web app (and the governed query engine) only ever reads this view, which joins the star schema
-- back into one wide row per order.  The normalised tables stay the source of truth; the app never touches them directly.

CREATE OR REPLACE VIEW orders AS
SELECT
  f.order_id,
  d.full_date          AS order_date,
  d.`year`             AS `year`,
  d.`month`            AS `month`,
  d.`quarter`          AS `quarter`,
  d.yr_month           AS yr_month,
  d.yr_quarter         AS yr_quarter,
  d.season             AS season,
  f.customer_id,
  f.customer_gender,
  f.customer_segment,
  g.region             AS region,
  g.country            AS country,
  p.category           AS category,
  p.sub_category       AS sub_category,
  p.product_name       AS product_name,
  f.unit_price,
  f.quantity,
  f.discount,
  f.revenue,
  f.cost,
  f.profit,
  f.profit_margin,
  f.shipping_cost,
  sm.shipping_method   AS shipping_method,
  f.shipping_days,
  pm.payment_method    AS payment_method,
  s.status             AS order_status,
  s.is_net             AS net_flag,
  f.loss_flag
FROM fact_orders f
JOIN dim_date            d  ON d.date_key = f.date_key
JOIN dim_geography       g  ON g.geo_id = f.geo_id
JOIN dim_product         p  ON p.product_id = f.product_id
JOIN dim_order_status    s  ON s.status_id = f.status_id
JOIN dim_shipping_method sm ON sm.shipping_method_id = f.shipping_method_id
JOIN dim_payment_method  pm ON pm.payment_method_id = f.payment_method_id;

-- Read-only introspection for the Admin > Database page.  SQL SECURITY DEFINER lets the low-privilege app account see sizes and
-- constraints of tables it is not allowed to read.
CREATE OR REPLACE SQL SECURITY DEFINER VIEW db_tables AS
SELECT table_name AS table_name, table_type AS table_type, engine AS engine, table_rows AS approx_rows,
       ROUND((data_length + index_length) / 1048576, 3) AS size_mb
FROM information_schema.tables
WHERE table_schema = '@@DB@@' AND table_name NOT IN ('schema_migrations');

CREATE OR REPLACE SQL SECURITY DEFINER VIEW db_constraints AS
SELECT table_name AS table_name, constraint_type AS constraint_type, constraint_name AS constraint_name
FROM information_schema.table_constraints
WHERE table_schema = '@@DB@@' AND constraint_type IN ('FOREIGN KEY', 'CHECK', 'UNIQUE');
