# Deployment Safety Rules

These rules are strictly enforced during any automated or manual deployment of the AIQM Exam Portal.

1. **Zero Destructive Database Operations**: Never execute `flask db downgrade`, `flask db stamp`, or any SQL `DROP` or `TRUNCATE` commands on the production database.
2. **Forward-Only Migrations**: Database schema changes only move forward. If a migration fails or causes issues, the fix must be a new forward-moving migration or a manual human intervention, never an automatic rollback.
3. **Mandatory Backups**: No database schema change can occur without a prior, verified PostgreSQL custom backup (`pg_dump -Fc`).
4. **Commit Lineage**: Only code that is part of the approved `origin/main` history or approved tags can be deployed.
5. **No Forced Pushes**: Never use `git push --force` or `git reset --hard` in production.
6. **Explicit Boundaries**: Deployments should occur during the designated maintenance window (22:00 to 06:00 IST) unless an emergency override is explicitly justified and logged.
