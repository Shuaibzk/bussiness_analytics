"""Clears the audit log (run before a demo so test traffic doesn't clutter it).  python -m app.reset_audit

Needs the schema OWNER account: the web application itself is not allowed to delete audit entries."""
from .db import get_db

with get_db(admin=True) as db:
    n = db.execute("DELETE FROM audit_log").rowcount
print(f"audit log cleared ({n} rows)")
