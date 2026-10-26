# Plus11 Supabase integration

This repository combines the PlusDash Next.js 16 frontend with Plus's full FastAPI/SQLAlchemy backend. Next.js is the only public listener. FastAPI binds to loopback and is called only by same-origin server-side BFF routes.

## Supabase setup

Create a Supabase project, enable the Email provider, and configure email/password sign-up. In Authentication > URL Configuration, set the site URL to the public Plus origin and allow the exact callback URLs `https://<your-origin>/api/auth/callback` and `http://localhost:3000/api/auth/callback` for local development. Configure `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` for Next.js. Set server-side `SUPABASE_URL` to the project origin and `DATABASE_URL` to the PostgreSQL connection string copied from the Supabase Dashboard's Connect dialog. Do not expose database credentials or secret/service-role keys through `NEXT_PUBLIC_*` variables or browser code.

The Python API validates access-token signatures against the project's JWKS, and checks issuer, expiry, audience, role, and UUID subject. The browser session is stored/refreshed through Supabase SSR cookies and the Next.js 16 `src/proxy.ts` entrypoint. Route handlers use verified claims before reading an access token for server-to-server FastAPI requests. Existing same-origin and CSRF protections remain on state-changing requests. Email and user metadata are used only for display; they are not identity or authorization keys.

## Database connection and schema

The backend uses SQLAlchemy with the Supabase PostgreSQL connection as its primary database. For the persistent FastAPI service, use the Supabase direct connection when the runtime network supports IPv6, or the session pooler when it does not. Keep TLS verification enabled. The engine uses a bounded pool and disables prepared statement caching so the selected pooler can be supported. Use the exact connection string and username from Supabase Connect; encode reserved characters in the password.

Production migrations are disabled at application startup. Back up and review the target before running `pnpm db:migrate` with the configured `DATABASE_URL`; run it as a single deployment step, not concurrently from multiple replicas. The migration helper is additive and also performs the documented page-provenance reconciliation. A new empty Supabase database must receive the schema and approved question/content data before learner practice will be useful. Do not assume setting `DATABASE_URL` copies data from SQLite or a previous MySQL database; a separate reviewed export/import and row-count/foreign-key validation is required for those existing records.

## Existing learner data

New Supabase users receive new learner profiles keyed by their verified Supabase Auth UUID. Existing Manus-linked practice history is not automatically linked to a new account and remains untouched in its original database. This avoids unsafe account matching by email. Learners who create new accounts start with new profiles.

## Local development

Install Node.js 22, pnpm 11.25, and Python 3.12. Run `pnpm install --frozen-lockfile` and `pnpm setup:python`, copy `.env.example` to an ignored `.env`, set the Supabase project URL and publishable key, and use an isolated SQLite URL such as `DATABASE_URL=sqlite:///./elevenplus.db` for local work. Set `SUPABASE_URL` to the same project origin if testing Supabase login locally. Add `http://localhost:3000/api/auth/callback` to Supabase's redirect allowlist. Start both services with `pnpm dev`.

## Checks

Run `pnpm lint`, `pnpm typecheck`, `pnpm build`, and `.venv/bin/pytest -q tests/`. Backend test fixtures use isolated SQLite databases and stub the JWKS verifier; they do not connect to or write to Supabase. Next's `/health` probes the private FastAPI readiness endpoint, which stays unready until the configured database schema exists.
