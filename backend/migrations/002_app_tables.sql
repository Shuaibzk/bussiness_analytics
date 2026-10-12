-- 002: application tables (users, sessions, audit trail, targets, chat history, knowledge base).

CREATE TABLE users (
  id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
  username       VARCHAR(32) NOT NULL,
  name           VARCHAR(80) NOT NULL,
  password_hash  VARCHAR(100) NOT NULL,
  role           ENUM('admin','executive','regional_manager','category_manager','operations') NOT NULL,
  scope_value    VARCHAR(60) NULL,
  active         TINYINT(1) NOT NULL DEFAULT 1,
  created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_users_username (username),
  -- a scoped role MUST have a scope and an unscoped role MUST NOT: the database refuses an inconsistent account
  CONSTRAINT chk_users_scope CHECK (
    (role IN ('regional_manager','category_manager') AND scope_value IS NOT NULL)
    OR (role NOT IN ('regional_manager','category_manager') AND scope_value IS NULL))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE sessions (
  jti         CHAR(32) NOT NULL,
  user_id     INT UNSIGNED NOT NULL,
  created_at  DOUBLE NOT NULL,
  last_seen   DOUBLE NOT NULL,
  revoked     TINYINT(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (jti),
  KEY ix_sessions_user (user_id),
  CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE login_attempts (
  username  VARCHAR(64) NOT NULL,
  ts        DOUBLE NOT NULL,
  KEY ix_login_attempts (username, ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE audit_log (
  id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  ts         DATETIME NOT NULL,
  username   VARCHAR(64) NULL,
  role       VARCHAR(30) NULL,
  scope      VARCHAR(80) NULL,
  action     VARCHAR(40) NOT NULL,
  detail     TEXT NULL,
  status     VARCHAR(20) NOT NULL,
  ms         DOUBLE NOT NULL DEFAULT 0,
  prev_hash  CHAR(64) NOT NULL,
  hash       CHAR(64) NOT NULL,
  PRIMARY KEY (id),
  KEY ix_audit_ts (ts),
  KEY ix_audit_user (username),
  KEY ix_audit_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE targets (
  id       INT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id  INT UNSIGNED NOT NULL,
  metric   ENUM('revenue','profit','orders') NOT NULL,
  `year`   SMALLINT NOT NULL,
  value    DECIMAL(16,2) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_target (user_id, metric, `year`),
  CONSTRAINT fk_targets_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
  CONSTRAINT chk_target_value CHECK (value > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE chat_messages (
  id       BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id  INT UNSIGNED NOT NULL,
  role     ENUM('user','assistant') NOT NULL,
  content  TEXT NOT NULL,
  meta     LONGTEXT NULL,
  ts       DOUBLE NOT NULL,
  rating   TINYINT NULL,
  comment  VARCHAR(300) NULL,
  PRIMARY KEY (id),
  KEY ix_chat_user (user_id, id),
  CONSTRAINT fk_chat_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
  CONSTRAINT chk_chat_rating CHECK (rating IS NULL OR rating IN (-1, 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE docs (
  id              VARCHAR(190) NOT NULL,
  title           VARCHAR(255) NOT NULL,
  topic           VARCHAR(80) NOT NULL,
  text            MEDIUMTEXT NOT NULL,
  scope_region    VARCHAR(60) NULL,
  scope_category  VARCHAR(60) NULL,
  needs           VARCHAR(255) NOT NULL DEFAULT '[]',
  embedding       LONGBLOB NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
