# Security Guide — Plus

## Secret Management

### Rules
1. **Never commit secrets** — use `.env` (gitignored) for local dev
2. **Use `.env.example`** for templates with placeholder values
3. **Rotate immediately** if a secret is committed to git
4. **Use secret managers** in production (Vercel env vars, AWS Secrets Manager, etc.)

### Credential Rotation Procedure (if exposed)

1. **Database password**: Supabase Dashboard → Database → Settings → Reset password
2. **Supabase keys**: Dashboard → Settings → API → Rotate keys
3. **Update `.env`** with new values
4. **Restart** all services
5. **Verify** connections work

### Historical Exposure
- `.env` was never tracked in git (verified via `git log --all -- .env`)
- If any credential was ever committed, treat it as compromised and rotate immediately

## Authentication & Authorization

### Model
- **Provider**: Supabase Auth (email/password)
- **Session**: Cookie-based via `@supabase/ssr`
- **Middleware**: `web/src/lib/supabase/middleware.ts` refreshes sessions
- **Protected routes**: Server-side checks in API routes

### Security Controls
- Session cookies are `httpOnly` and `secure` in production
- CSRF protection via SameSite cookie attribute
- Open redirect prevention in callback routes
- Rate limiting on auth endpoints (recommended)

## Row Level Security (RLS)

### Requirements
- RLS must be enabled on all exposed tables
- Policies must enforce user-level access
- Service-role key must never be exposed to browser
- Test both allowed and denied operations

### Verification
```sql
-- Check RLS status
SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public';
```

## API Security

### Controls
- Input validation on all endpoints
- Parameterized SQL (no string interpolation)
- Request size limits
- CORS configured only where needed
- No wildcard origins with credentials
- Safe error responses (no stack traces to client)

### Rate Limiting
- Auth endpoints: 5 requests/minute per IP
- API endpoints: 100 requests/minute per user
- Use Redis or managed service for distributed rate limiting

## SSL & Database Access

### TLS
- Always verify TLS certificates (never disable)
- Use Supabase's CA certificate for direct connections
- Replace machine-specific cert paths with portable config

### Database
- Use Supabase client for browser access
- Use direct connections only from backend
- Prefer session pooling for long-lived connections
- Never use transaction pooler for migrations
