-- 005: reporting table.
-- Joining six tables on every dashboard query made the view ~3.5x slower than a single-table scan (62 ms vs 17 ms measured).
-- Standard warehouse practice: keep the star schema as the source of truth and serve reports from a denormalised copy that is
-- rebuilt from it after every load (MariaDB has no materialized views, so ingest.refresh_reporting() does this explicitly).
-- The old view becomes the *definition* of the copy (v_orders_flat); the app only ever reads the table `orders`.

RENAME TABLE orders TO v_orders_flat;

CREATE TABLE orders (
  order_id          VARCHAR(16) NOT NULL,
  order_date        DATE NOT NULL,
  `year`            SMALLINT NOT NULL,
  `month`           TINYINT NOT NULL,
  `quarter`         CHAR(2) NOT NULL,
  yr_month          CHAR(7) NOT NULL,
  yr_quarter        CHAR(7) NOT NULL,
  season            VARCHAR(8) NOT NULL,
  customer_id       VARCHAR(16) NOT NULL,
  customer_gender   ENUM('Male','Female') NOT NULL,
  customer_segment  ENUM('New','Regular','Premium','VIP') NOT NULL,
  region            VARCHAR(40) NOT NULL,
  country           VARCHAR(40) NOT NULL,
  category          VARCHAR(60) NOT NULL,
  sub_category      VARCHAR(60) NOT NULL,
  product_name      VARCHAR(80) NOT NULL,
  unit_price        DECIMAL(10,2) NOT NULL,
  quantity          SMALLINT UNSIGNED NOT NULL,
  discount          DECIMAL(3,2) NOT NULL,
  revenue           DECIMAL(12,2) NOT NULL,
  cost              DECIMAL(12,2) NOT NULL,
  profit            DECIMAL(12,2) NOT NULL,
  profit_margin     DECIMAL(8,2) NULL,
  shipping_cost     DECIMAL(8,2) NOT NULL,
  shipping_method   VARCHAR(20) NOT NULL,
  shipping_days     TINYINT UNSIGNED NOT NULL,
  payment_method    VARCHAR(30) NOT NULL,
  order_status      VARCHAR(20) NOT NULL,
  net_flag          TINYINT(1) NOT NULL,
  loss_flag         TINYINT(1) NOT NULL,
  PRIMARY KEY (order_id),
  KEY ix_orders_region (region),
  KEY ix_orders_category (category),
  KEY ix_orders_year_month (`year`, `month`),
  KEY ix_orders_status (order_status),
  KEY ix_orders_country (country),
  KEY ix_orders_segment (customer_segment),
  KEY ix_orders_customer (customer_id),
  KEY ix_orders_date (order_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO orders SELECT * FROM v_orders_flat;

-- table-level privileges follow the name, but state them explicitly so the migration is self-describing
GRANT SELECT ON `@@DB@@`.orders TO '@@APP_USER@@'@'localhost', '@@APP_USER@@'@'127.0.0.1';
