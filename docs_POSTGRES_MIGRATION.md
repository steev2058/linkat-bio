# Postgres Migration Notes

Current MVP uses SQLite with normalized tables:
- users
- pages
- links
- vouchers
- analytics_events

To migrate:
1. Replace sqlite layer (`app/db.py`) with SQLAlchemy models/session.
2. Use `DATABASE_URL` env var and psycopg driver.
3. Add Alembic migrations for schema versioning.
4. Keep same business rules in `app/services.py`.
