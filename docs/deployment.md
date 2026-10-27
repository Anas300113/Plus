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
cd web
npm ci
npm run build
npm start
```

### Backend
```bash
pip install -r requirements.txt
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8001
```

### Full stack
```bash
pnpm dev   # Development
pnpm start # Production (via supervise.py)
```

## Database Migrations

Run migrations before deploying new schema:

```bash
# Production (opt-in)
PLUS_RUN_MIGRATIONS=1 python -m src.core.migrate
```

**WARNING**: Migrations are additive. Review `src/core/migrations.py` before running.

## Health Checks

- Frontend: `GET /` → 200
- Backend: `GET /api/health` → 200
- Database: Check Supabase dashboard

## Rollback Strategy

1. Revert to previous git commit
2. Rebuild and redeploy
3. Database: Restore from Supabase backup (if needed)

## Backup & Recovery

- Supabase provides automatic daily backups
- Point-in-time recovery available on Pro plan
- Test restore procedure quarterly
- Keep `DATABASE_URL` credentials in a secret manager (not in git)
