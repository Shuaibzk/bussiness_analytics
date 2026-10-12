-- ============================================================================================================================
--  PANORAMA - DATABASE DEMO.   Run it with:  db_demo.bat        (or paste any section into the mysql client / phpMyAdmin SQL tab)
--  Everything here is read-only except section 8, which ATTEMPTS bad writes inside a transaction that is always rolled back.
-- ============================================================================================================================

SELECT '1. WHAT IS IN THE DATABASE (star schema + reporting table + application tables)' AS section;
SELECT table_name AS `table`,
       CASE WHEN table_name LIKE 'fact\_%' THEN 'FACT' WHEN table_name LIKE 'dim\_%' THEN 'DIMENSION'
            WHEN table_name = 'orders' THEN 'REPORTING TABLE' WHEN table_type = 'VIEW' THEN 'VIEW' ELSE 'APPLICATION' END AS kind,
       engine, table_rows AS approx_rows, ROUND((data_length + index_length) / 1048576, 2) AS size_mb
FROM information_schema.tables WHERE table_schema = 'panorama'
ORDER BY FIELD(CASE WHEN table_name LIKE 'fact\_%' THEN 'FACT' WHEN table_name LIKE 'dim\_%' THEN 'DIMENSION'
                    WHEN table_name = 'orders' THEN 'REPORTING TABLE' WHEN table_type = 'VIEW' THEN 'VIEW' ELSE 'APPLICATION' END,
                'FACT', 'DIMENSION', 'REPORTING TABLE', 'APPLICATION', 'VIEW'), table_name;

SELECT '2. EXACT ROW COUNTS' AS section;
SELECT 'fact_orders' AS `table`, COUNT(*) AS `rows` FROM fact_orders
UNION ALL SELECT 'dim_customer', COUNT(*) FROM dim_customer
UNION ALL SELECT 'dim_product', COUNT(*) FROM dim_product
UNION ALL SELECT 'dim_geography', COUNT(*) FROM dim_geography
UNION ALL SELECT 'dim_date', COUNT(*) FROM dim_date
UNION ALL SELECT 'dim_order_status', COUNT(*) FROM dim_order_status
UNION ALL SELECT 'dim_shipping_method', COUNT(*) FROM dim_shipping_method
UNION ALL SELECT 'dim_payment_method', COUNT(*) FROM dim_payment_method
UNION ALL SELECT 'orders (reporting copy)', COUNT(*) FROM orders;

SELECT '3. THE FACT TABLE DEFINITION: columns, generated columns, foreign keys and CHECK rules in one place' AS section;
SHOW CREATE TABLE fact_orders\G

SELECT '4. FOREIGN KEYS (referential integrity)' AS section;
SELECT k.table_name AS `table`, k.column_name AS `column`, k.referenced_table_name AS references_table,
       k.referenced_column_name AS references_column, r.delete_rule AS on_delete
FROM information_schema.key_column_usage k
JOIN information_schema.referential_constraints r ON r.constraint_schema = k.table_schema AND r.constraint_name = k.constraint_name
WHERE k.table_schema = 'panorama' AND k.referenced_table_name IS NOT NULL
ORDER BY k.table_name, k.column_name;

SELECT '5. CHECK RULES (the database refuses data that breaks the business rules)' AS section;
SELECT table_name AS `table`, constraint_name AS rule_name, check_clause AS rule
FROM information_schema.check_constraints WHERE constraint_schema = 'panorama' ORDER BY table_name, constraint_name;

SELECT '6. THE NET / GROSS BUSINESS RULE LIVES IN THE DATABASE (dim_order_status.is_net)' AS section;
SELECT * FROM dim_order_status;

SELECT '7a. A REPORT FROM THE REPORTING TABLE (this is what the dashboard reads): net revenue and profit by region' AS section;
SELECT region, COUNT(*) AS orders, SUM(CASE WHEN net_flag = 1 THEN revenue ELSE 0 END) AS net_revenue,
       SUM(CASE WHEN net_flag = 1 THEN profit ELSE 0 END) AS net_profit
FROM orders GROUP BY region ORDER BY net_revenue DESC;

SELECT '7b. THE SAME NUMBERS COMPUTED FROM THE STAR SCHEMA (fact joined to dimensions): they must match' AS section;
SELECT g.region, COUNT(*) AS orders, SUM(CASE WHEN s.is_net = 1 THEN f.revenue ELSE 0 END) AS net_revenue,
       SUM(CASE WHEN s.is_net = 1 THEN f.profit ELSE 0 END) AS net_profit
FROM fact_orders f
JOIN dim_geography g ON g.geo_id = f.geo_id
JOIN dim_order_status s ON s.status_id = f.status_id
GROUP BY g.region ORDER BY net_revenue DESC;

SELECT '7c. GENERATED COLUMNS are computed by the database (profit_margin, loss_flag)' AS section;
SELECT order_id, revenue, cost, profit, profit_margin, loss_flag FROM fact_orders ORDER BY profit LIMIT 3;

SELECT '8. TRY TO BREAK IT - every statement below must be REFUSED (inside a transaction that is rolled back anyway)' AS section;
START TRANSACTION;
-- (a) a discount of 500% violates CHECK chk_discount
UPDATE fact_orders SET discount = 5 WHERE order_id = 'ORD-000001';
-- (b) deleting a country that orders still reference violates the foreign key
DELETE FROM dim_geography WHERE country = 'Japan';
-- (c) a regional manager without a region violates CHECK chk_users_scope
INSERT INTO users (username, name, password_hash, role) VALUES ('intruder', 'x', 'x', 'regional_manager');
-- (d) revenue that does not equal price x quantity x (1 - discount) violates CHECK chk_revenue_rule
UPDATE fact_orders SET revenue = 1 WHERE order_id = 'ORD-000002';
ROLLBACK;
SELECT 'nothing was changed' AS result, (SELECT COUNT(*) FROM fact_orders) AS fact_rows, (SELECT COUNT(*) FROM dim_geography) AS geographies;

SELECT '9. LEAST PRIVILEGE: what the web application account may do (note: no DROP / ALTER / CREATE, no fact or dimension tables, audit_log is INSERT + SELECT only)' AS section;
-- (deliberately NOT "SHOW GRANTS": it prints the account's password hash)
SELECT table_name AS `table`, GROUP_CONCAT(privilege_type ORDER BY privilege_type SEPARATOR ', ') AS privileges
FROM information_schema.table_privileges WHERE grantee = '''panorama_app''@''localhost''' GROUP BY table_name ORDER BY table_name;

SELECT '10. VERSIONED MIGRATIONS (each file is checksummed; editing an applied one is detected)' AS section;
SELECT version, name, applied_at, LEFT(checksum, 12) AS checksum FROM schema_migrations ORDER BY version;

SELECT '11. HASH-CHAINED AUDIT LOG (each row stores the hash of the one before it)' AS section;
SELECT id, ts, username, action, status, LEFT(prev_hash, 10) AS prev_hash, LEFT(hash, 10) AS hash FROM audit_log ORDER BY id DESC LIMIT 5;

SELECT '12. TWO THINGS THE DATA TAUGHT US - (a) customer segment is not stable, (b) the latest months look incomplete' AS section;
SELECT COUNT(*) AS customers, SUM(segments > 1) AS customers_with_more_than_one_segment,
       ROUND(100 * SUM(segments > 1) / COUNT(*), 1) AS pct
FROM (SELECT customer_id, COUNT(DISTINCT customer_segment) AS segments FROM fact_orders GROUP BY customer_id) t;
SELECT yr_month AS month, COUNT(*) AS orders FROM orders GROUP BY yr_month ORDER BY yr_month DESC LIMIT 12;
