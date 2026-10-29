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

### Optional
| Variable | Description |
|---|---|
| `SUPABASE_DB_SSLROOTCERT` | SSL cert path for DB connections |
| `PLUS_REVIEWER_TOKEN` | Token for question review operations |
| `PORT` | Frontend port (default: 3000) |

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

## Rollback Strategy

1. Revert to previous git commit
2. Rebuild and redeploy
3. Database: Restore from Supabase backup (if needed)

## Backup & Recovery

- Supabase provides automatic daily backups
- Point-in-time recovery available on Pro plan
- Test restore procedure quarterly
- Keep `DATABASE_URL` credentials in a secret manager (not in git)
