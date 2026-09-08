---
name: production-deployment-safety
description: Deterministic, safe workflow for deploying code and database changes to the production Exam Portal.
---

# Production Deployment Safety Skill

Use this skill whenever you are asked to deploy changes to the production environment of the AIQM Exam Portal.

## Objective
To safely deploy code changes while strictly ensuring database migration parity, maintaining backups, and adhering to strict non-destructive protocols.

## Core Rules
1. **Zero Destructive Commands**: Never run `flask db downgrade`, `flask db stamp`, or any DROP table/database commands.
2. **Forward-Only Database Migrations**: Database migrations are strictly forward-only. Never auto-rollback.
3. **Commit Verification**: Only deploy explicit commits that exist in `origin/main` history.
4. **Night-Only Window**: Deployments are blocked outside 22:00 to 06:00 IST unless explicitly overridden.

## Deployment Protocol
Whenever a user requests a deployment:

1. **Information Gathering**:
   - Verify the target commit SHA or tag.
   - Run `git fetch origin` to ensure you have the latest history.
   - You MUST run `python .agents/skills/production-deployment-safety/scripts/check_migration_sync.py` locally first to verify the migration status.
2. **User Confirmation**: Present a pre-flight deployment summary including:
   - Target Commit SHA and Tag
   - Migration Status (Required or not)
   - Current time vs Deployment Window
   Ask the user: "Proceed with deployment of commit <SHA>?"
3. **Execution**:
   Once approved, execute the deployment using the orchestrator:
   ```bash
   python .agents/skills/production-deployment-safety/scripts/deploy_runner.py --commit <SHA>
   ```
   *Note: If deploying outside the window, you must append `--emergency-override --override-reason "user approved"`*
4. **Post-Deployment**:
   If the script exits successfully (exit code 0), report success. If it fails, report the error and DO NOT attempt automatic recovery or rollback of migrations. Follow the instructions in `references/disaster_recovery_runbook.md` if human intervention is needed.
