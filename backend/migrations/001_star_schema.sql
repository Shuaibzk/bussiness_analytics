-- 001: analytical core - a star schema (one fact table, small dimensions) with integrity enforced by the database itself.
--
-- Modelling note: in this dataset a customer's SEGMENT and GENDER are not stable (41% of customers appear with more than one
-- segment), so they are order-level attributes on the fact table ("as recorded on the order") instead of columns of
-- dim_customer.  The business rule "net sales exclude returned / cancelled orders" lives in dim_order_status.is_net.

CREATE TABLE dim_geography (
  geo_id        SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
  region        VARCHAR(40) NOT NULL,
  country       VARCHAR(40) NOT NULL,
  PRIMARY KEY (geo_id),
  UNIQUE KEY uq_geo_country (country),
  KEY ix_geo_region (region)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE dim_product (
  product_id    SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
  product_name  VARCHAR(80) NOT NULL,
  sub_category  VARCHAR(60) NOT NULL,
  category      VARCHAR(60) NOT NULL,
  PRIMARY KEY (product_id),
  UNIQUE KEY uq_product_name (product_name),
  KEY ix_product_category (category),
  KEY ix_product_subcategory (sub_category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE dim_customer (
  customer_id       VARCHAR(16) NOT NULL,
  first_order_date  DATE NOT NULL,
  PRIMARY KEY (customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE dim_date (
  date_key      INT NOT NULL,                       -- yyyymmdd
  full_date     DATE NOT NULL,
  `year`        SMALLINT NOT NULL,
  `quarter`     CHAR(2) NOT NULL,
  `month`       TINYINT NOT NULL,
  month_name    CHAR(3) NOT NULL,
  season        VARCHAR(8) NOT NULL,
  yr_month      CHAR(7) NOT NULL,                   -- 2023-05  (YEAR_MONTH is a reserved word in MariaDB)
  yr_quarter    CHAR(7) NOT NULL,                   -- 2023-Q2
  PRIMARY KEY (date_key),
  UNIQUE KEY uq_date_full (full_date),
  KEY ix_date_year_month (`year`, `month`),
  CONSTRAINT chk_date_month CHECK (`month` BETWEEN 1 AND 12)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE dim_order_status (
  status_id     TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
  status        VARCHAR(20) NOT NULL,
  is_net        TINYINT(1) NOT NULL,                -- 1 = counts as realised (net) sales
  PRIMARY KEY (status_id),
  UNIQUE KEY uq_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE dim_shipping_method (
  shipping_method_id TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
  shipping_method    VARCHAR(20) NOT NULL,
  PRIMARY KEY (shipping_method_id),
  UNIQUE KEY uq_shipping_method (shipping_method)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE dim_payment_method (
  payment_method_id TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
  payment_method    VARCHAR(30) NOT NULL,
  PRIMARY KEY (payment_method_id),
  UNIQUE KEY uq_payment_method (payment_method)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE fact_orders (
  order_id            VARCHAR(16) NOT NULL,
  date_key            INT NOT NULL,
  geo_id              SMALLINT UNSIGNED NOT NULL,
  product_id          SMALLINT UNSIGNED NOT NULL,
  customer_id         VARCHAR(16) NOT NULL,
  status_id           TINYINT UNSIGNED NOT NULL,
  shipping_method_id  TINYINT UNSIGNED NOT NULL,
  payment_method_id   TINYINT UNSIGNED NOT NULL,
  customer_segment    ENUM('New','Regular','Premium','VIP') NOT NULL,
  customer_gender     ENUM('Male','Female') NOT NULL,
  quantity            SMALLINT UNSIGNED NOT NULL,
  unit_price          DECIMAL(10,2) NOT NULL,
  discount            DECIMAL(3,2) NOT NULL,
  revenue             DECIMAL(12,2) NOT NULL,
  cost                DECIMAL(12,2) NOT NULL,
  profit              DECIMAL(12,2) NOT NULL,
  shipping_cost       DECIMAL(8,2) NOT NULL,
  shipping_days       TINYINT UNSIGNED NOT NULL,
  profit_margin       DECIMAL(8,2) AS (CASE WHEN revenue = 0 THEN NULL ELSE ROUND(profit / revenue * 100, 2) END) PERSISTENT,
  loss_flag           TINYINT(1) AS (profit < 0) PERSISTENT,
  PRIMARY KEY (order_id),
  KEY ix_fact_date (date_key),
  KEY ix_fact_geo_date (geo_id, date_key),
  KEY ix_fact_product_date (product_id, date_key),
  KEY ix_fact_customer (customer_id),
  KEY ix_fact_status (status_id),
  KEY ix_fact_shipping (shipping_method_id),
  KEY ix_fact_payment (payment_method_id),
  KEY ix_fact_segment (customer_segment),
  CONSTRAINT fk_fact_date     FOREIGN KEY (date_key)           REFERENCES dim_date (date_key),
  CONSTRAINT fk_fact_geo      FOREIGN KEY (geo_id)             REFERENCES dim_geography (geo_id),
  CONSTRAINT fk_fact_product  FOREIGN KEY (product_id)         REFERENCES dim_product (product_id),
  CONSTRAINT fk_fact_customer FOREIGN KEY (customer_id)        REFERENCES dim_customer (customer_id),
  CONSTRAINT fk_fact_status   FOREIGN KEY (status_id)          REFERENCES dim_order_status (status_id),
  CONSTRAINT fk_fact_ship     FOREIGN KEY (shipping_method_id) REFERENCES dim_shipping_method (shipping_method_id),
  CONSTRAINT fk_fact_pay      FOREIGN KEY (payment_method_id)  REFERENCES dim_payment_method (payment_method_id),
  CONSTRAINT chk_qty          CHECK (quantity > 0),
  CONSTRAINT chk_price        CHECK (unit_price >= 0),
  CONSTRAINT chk_discount     CHECK (discount BETWEEN 0 AND 1),
  CONSTRAINT chk_ship_cost    CHECK (shipping_cost >= 0),
  CONSTRAINT chk_ship_days    CHECK (shipping_days <= 60),
  CONSTRAINT chk_revenue_rule CHECK (ABS(revenue - ROUND(unit_price * quantity * (1 - discount), 2)) <= 0.05),
  CONSTRAINT chk_profit_rule  CHECK (ABS(profit - (revenue - cost)) <= 0.05)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
