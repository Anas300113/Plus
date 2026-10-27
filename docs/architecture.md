# Architecture — Plus

## Overview

Plus is a monorepo combining a Python FastAPI backend with a Next.js frontend, backed by Supabase (PostgreSQL + Auth).

## Component Responsibilities

### `web/` — Next.js Frontend
- **UI**: React components, pages, layouts
- **Server components**: Data fetching, auth checks
- **Next.js API routes** (`web/src/app/api/`): BFF (Backend for Frontend) — proxies to Python backend or handles auth directly
- **Supabase client** (`web/src/lib/supabase/`): Browser-safe auth + data access

### `src/` — Python Backend
- **FastAPI app** (`src/api/main.py`): REST API for learning engine, practice sessions, review queue
- **Domain logic** (`src/learning/`, `src/assessment/`, `src/curriculum/`): Business rules
- **Database** (`src/core/database.py`, `src/core/migrate.py`): SQLAlchemy models + migrations
- **Knowledge engine** (`src/knowledge/`, `src/pipeline/`): Content ingestion and processing

### Supabase
- **Auth**: User identity via `@supabase/ssr`
- **Database**: PostgreSQL with RLS policies

## Data Flow

```
Browser → Next.js (web/) → Next.js API Routes → Python FastAPI (src/) → Supabase Postgres
```

**Canonical path**: Browser → Next.js API route → Python FastAPI → Supabase/PostgreSQL

**Exception**: Supabase Auth is called directly from the browser via `@supabase/ssr` for session management.

## Authentication Model

- **Provider**: Supabase Auth (email/password)
- **Session**: `@supabase/ssr` with cookie-based sessions
- **Middleware**: `web/src/lib/supabase/middleware.ts` refreshes sessions
- **Protected routes**: Server-side checks in Next.js API routes + Python backend

## Database Access

- **Python backend**: Uses SQLAlchemy with `DATABASE_URL` (direct Postgres connection)
- **Next.js**: Uses Supabase client for auth only; data goes through Python backend
- **Migrations**: Python `src/core/migrate.py` (additive, version-controlled)

## External Services

- **Supabase**: Auth + PostgreSQL database
- **FastAPI backend**: Runs on port 8001 (localhost)
- **Next.js frontend**: Runs on port 3000

## Deployment

- **Frontend**: Next.js standalone build → Vercel or container
- **Backend**: FastAPI via uvicorn → container or VM
- **Database**: Supabase managed Postgres
