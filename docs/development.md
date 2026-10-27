# Development Guide — Plus

## Prerequisites

- Python 3.11+
- Node.js 20+
- pnpm 9+ (or npm)
- A Supabase project (for auth + database)

## Setup

### 1. Clone and install

```bash
git clone https://github.com/Anas300113/Plus.git
cd Plus
```

### 2. Python backend

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Frontend

```bash
cd web
npm install
cd ..
```

### 4. Environment

```bash
cp .env.example .env
# Edit .env with your Supabase credentials
cp web/.env.example web/.env
# Edit web/.env with your Supabase public keys
```

### 5. Run locally

**Option A: Full stack (recommended)**

```bash
pnpm dev
# Starts FastAPI on :8001 + Next.js on :3000
```

**Option B: Frontend only**

```bash
cd web && npm run dev
# Next.js on :3000 (requires backend separately)
```

**Option C: Backend only**

```bash
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8001
```

### 6. Run tests

```bash
# Python tests
pnpm api:test

# Frontend
cd web && npm run lint
cd web && npm run typecheck
cd web && npm run build
```

## Common Issues

### Database connection fails (IPv6)
Supabase DB host is IPv6-only. Direct psycopg2 connections may fail locally.
Use the Supabase client or MCP SQL editor instead.

### Backend not starting
Ensure `.venv` is activated and FastAPI dependencies are installed:
```bash
pip install fastapi sqlalchemy uvicorn
```

### Auth callback errors
Whitelist `http://localhost:3000/api/auth/callback` in Supabase Dashboard → Authentication → URL Configuration.

## Troubleshooting

- **Port conflict**: Change `PLUS_API_PORT` or `PORT` in `.env`
- **Module not found**: Run `pip install -r requirements.txt` again
- **TypeScript errors**: Run `cd web && npm run typecheck`
