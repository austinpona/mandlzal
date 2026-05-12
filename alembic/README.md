# Alembic migrations

This directory holds the schema migrations for the Mandlzi database.

## Common commands

```bash
# Apply all pending migrations to the database in DATABASE_URL
alembic upgrade head

# Roll back one migration
alembic downgrade -1

# Show current revision applied to the DB
alembic current

# Show history
alembic history --verbose

# Create a new migration from model diff (review the file before committing!)
alembic revision --autogenerate -m "add foo column"

# Stamp the DB as being at head without running anything (use after a
# manual create-all in dev so future `upgrade head` is a no-op)
alembic stamp head
```

## Notes

- The database URL is loaded from `app.config.settings.DATABASE_URL` (env var
  `DATABASE_URL` or `.env`). `alembic.ini` only contains a placeholder.
- For SQLite we enable `render_as_batch=True` so that ALTER TABLE works.
- The app's `init_db()` (which simply calls `Base.metadata.create_all`) is
  kept as a developer convenience fallback when `RUN_INIT_DB=1`. Production
  deployments should use `alembic upgrade head` and leave `RUN_INIT_DB`
  unset so the app never touches the schema implicitly.
