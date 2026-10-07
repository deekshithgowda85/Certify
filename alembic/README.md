# Database Migrations

This directory contains the Alembic environment and ordered schema migrations for PostgreSQL.

## Apply migrations

Compose applies `upgrade head` as part of API startup when `RUN_MIGRATIONS` is enabled. To run it manually from the repository root:

```powershell
$env:PYTHONPATH = "api"
alembic -c alembic/alembic.ini upgrade head
```

Check the applied revision with:

```powershell
$env:PYTHONPATH = "api"
alembic -c alembic/alembic.ini current
```

## Migration policy

- Add a new numbered revision; do not edit migrations that may already have been applied.
- Implement a matching downgrade where practical.
- Test upgrades against an empty PostgreSQL database and preserve existing rows.
- Migrations are automatically run by the API lifespan when `RUN_MIGRATIONS=true`; disable that only for controlled deployments where migrations are managed separately.

The current chain creates jobs/recipients, adds users and job ownership, then adds persisted job idempotency fields.
