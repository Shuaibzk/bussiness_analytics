-- 004: least privilege for the web application account.
-- It can read the flat `orders` view and the introspection views, and write only its own operational tables.
-- It can NOT read the fact/dimension tables directly, change the schema, delete users, or edit / delete audit entries
-- (audit_log is INSERT + SELECT only: the application cannot rewrite its own history).

GRANT SELECT ON `@@DB@@`.orders             TO '@@APP_USER@@'@'localhost', '@@APP_USER@@'@'127.0.0.1';
GRANT SELECT ON `@@DB@@`.db_tables          TO '@@APP_USER@@'@'localhost', '@@APP_USER@@'@'127.0.0.1';
GRANT SELECT ON `@@DB@@`.db_constraints     TO '@@APP_USER@@'@'localhost', '@@APP_USER@@'@'127.0.0.1';
GRANT SELECT ON `@@DB@@`.schema_migrations  TO '@@APP_USER@@'@'localhost', '@@APP_USER@@'@'127.0.0.1';
GRANT SELECT, INSERT, UPDATE ON `@@DB@@`.users           TO '@@APP_USER@@'@'localhost', '@@APP_USER@@'@'127.0.0.1';
GRANT SELECT, INSERT, UPDATE, DELETE ON `@@DB@@`.sessions       TO '@@APP_USER@@'@'localhost', '@@APP_USER@@'@'127.0.0.1';
GRANT SELECT, INSERT, DELETE ON `@@DB@@`.login_attempts         TO '@@APP_USER@@'@'localhost', '@@APP_USER@@'@'127.0.0.1';
GRANT SELECT, INSERT ON `@@DB@@`.audit_log                      TO '@@APP_USER@@'@'localhost', '@@APP_USER@@'@'127.0.0.1';
GRANT SELECT, INSERT, UPDATE, DELETE ON `@@DB@@`.targets        TO '@@APP_USER@@'@'localhost', '@@APP_USER@@'@'127.0.0.1';
GRANT SELECT, INSERT, UPDATE, DELETE ON `@@DB@@`.chat_messages  TO '@@APP_USER@@'@'localhost', '@@APP_USER@@'@'127.0.0.1';
GRANT SELECT, INSERT, DELETE ON `@@DB@@`.docs                   TO '@@APP_USER@@'@'localhost', '@@APP_USER@@'@'127.0.0.1';
