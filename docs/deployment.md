# Deployment Guide — Plus

## Hosting Targets

- **Frontend**: Vercel (Next.js standalone build) or Docker container
- **Backend**: FastAPI via uvicorn on a VM or container
- **Database**: Supabase managed PostgreSQL
- **Auth**: Supabase Auth

## Required Environment Variables

### Production (all required)
| Variable | Service | Description |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Frontend | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Frontend | Supabase publishable key |
| `SUPABASE_URL` | Backend | Supabase project URL |
| `DATABASE_URL` | Backend | Postgres connection string |
| `PLUS_DB_SSLMODE` | Backend | `require` by default; use `verify-full` only with the Supabase CA bundle |
| `PLUS11_AUTH_ALLOWED_ORIGINS` | Backend | Allowed CORS origins |
| `PLUS_API_BASE_URL` | Frontend | Backend URL |
| `PLUS_API_PORT` | Backend | Backend port |
| `PLUS_RUN_MIGRATIONS` | Backend | Set to `1` for first deploy, `0` after |
| `PLUS_REAL_STUDENT_DATA` | Backend | Must be `1` for production learner data |
| `PLUS_REQUIRE_STUDENT_IDENTITY` | Backend | Must be `1` for production learner data |

### Optional
| Variable | Description |
|---|---|
| `SUPABASE_DB_SSLROOTCERT` | SSL cert path for DB connections |
| `PLUS_REVIEWER_TOKEN` | Token for question review operations |
| `PORT` | Frontend port (default: 3000) |
| `PLUS_DB_POOL_SIZE` / `PLUS_DB_MAX_OVERFLOW` | PostgreSQL pool bounds (defaults 5 / 5) |
| `PLUS_DB_STATEMENT_TIMEOUT_MS` | PostgreSQL statement timeout (default 15000) |

## Build & Start Commands

### Frontend
```bash
pnpm install --frozen-lockfile
pnpm build
node server.js
```

### Backend
```bash
pip install -r requirements.txt
python -m src.core.migrate
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8001
```

### Full stack
```bash
pnpm dev   # Development
pnpm start # Production (via supervise.py)
```

## Database Migrations

Use the Supabase Dashboard's **direct** database connection for migrations,
not the transaction pooler. The application can use a pooled connection, but
schema DDL and the migration advisory lock must run against the direct/session
endpoint. URL-encode the database password and keep the connection string in a
secret manager.

Run migrations before deploying new schema:

```bash
# Production (opt-in)
PLUS_RUN_MIGRATIONS=1 python -m src.core.migrate
```

**WARNING**: Migrations are additive. Review `src/core/migrations.py` before running.
The migration command is idempotent and records applied actions in
`schema_migrations`; run it once as a deployment step, then set
`PLUS_RUN_MIGRATIONS=0` for normal application startup.

## Health Checks

- Frontend: `GET /` → 200
- Backend: `GET /api/health` → 200
- Backend readiness: `GET /api/ready` → 200 only after the database connection and
  required learner tables are available
- Database: Check Supabase dashboard and confirm the migration step completed

For a deployed stack, run the unauthenticated checks from the repository root:

```bash
python scripts/smoke_test.py \
  --web https://plus.example.com \
  --api https://api.example.com
```

The smoke test intentionally does not test learner data. Complete the
authenticated browser checklist below using a staging account before allowing
production traffic.

## Go-live sequence

### Stage 1 — Prepare Supabase

1. Create a dedicated staging Supabase project and a separate production
   project. Do not use production credentials in local development.
2. Configure Supabase Auth email/password settings and add the exact frontend
   callback URL under Authentication → URL Configuration.
3. Copy the **direct/session** PostgreSQL connection string from Supabase.
   URL-encode the database password. Keep the transaction pooler out of the
   migration job.
4. Store secrets in the hosting provider's secret manager. Never put
   `DATABASE_URL`, reviewer tokens, or private keys in GitHub Actions logs.

### Stage 2 — Deploy staging

1. Build the exact commit intended for release.
2. Set `PLUS_RUN_MIGRATIONS=1` for the one-time migration job, with
   `PLUS_DB_SSLMODE=require` unless the Supabase CA bundle is mounted.
3. Run `python -m src.core.migrate` and save its output as the release record.
4. Set `PLUS_RUN_MIGRATIONS=0` for the long-running application process.
5. Deploy the backend and frontend, then run `scripts/smoke_test.py`.
6. Create a staging learner account and verify signup, login, logout, profile
   update, dashboard, mini-lesson, practice answers, retries, completion,
   reviews, progress, and the Friday combined test.
7. Verify authorization: an expired/altered JWT is rejected, a learner cannot
   access another learner's session, CSRF-protected mutations reject missing or
   invalid tokens, and pending/reference-only questions never appear.
8. Confirm Supabase database backups, auth email delivery, logs, and resource
   usage before promoting the release.

### Stage 3 — Production cutover

1. Take or verify a current Supabase backup and record the backup timestamp.
2. Put the release in maintenance or keep the current version serving traffic.
3. Run the migration job against the production **direct/session** connection.
4. Check `/api/ready`; do not route traffic if it is not `200`.
5. Deploy the backend and frontend using the same tested commit and set
   `PLUS_RUN_MIGRATIONS=0` on the application process.
6. Run the smoke test and one authenticated canary account check.
7. Monitor error rate, latency, database connections, Supabase Auth errors,
   and failed learner mutations for at least 30 minutes.
8. Announce availability only after the canary and monitoring window pass.

### Stage 4 — Rollback

1. If application code fails but the schema is compatible, redeploy the prior
   application image/commit without reverting the database.
2. If a migration caused data or schema damage, stop writes, preserve logs,
   restore to a new Supabase staging project first, and validate the restore.
3. Only restore production after the staging restore passes the smoke test and
   learner authorization checks. Never run destructive rollback SQL casually.
4. Rotate any credential that appeared in logs or was exposed during a failed
   deployment.

### Release acceptance criteria

The release is considered production-ready only when all of the following are
true: CI is green; staging migration and browser checks pass; production
`/api/ready` is green; the smoke test passes; backups are verified; the
production frontend and backend use the same commit; no secrets are present in
the repository; and the rollback owner and contact path are recorded.

## Rollback Strategy

1. Revert to previous git commit
2. Rebuild and redeploy
3. Database: Restore from Supabase backup (if needed)

## Backup & Recovery

- Supabase provides automatic daily backups
- Point-in-time recovery available on Pro plan
- Test restore procedure quarterly
- Keep `DATABASE_URL` credentials in a secret manager (not in git)
