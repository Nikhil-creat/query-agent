# Query — Chat With Your Data

An AI agent that lets you ask plain-English questions about a dataset and
get back a real SQL query, a chart, and a written insight — with the
query it ran always shown, never hidden.

```
"What's total revenue by region?"
        │
        ▼
 ┌─────────────────┐      ┌──────────────┐      ┌───────────────────┐
 │  1. NL → SQL     │ ───▶ │  2. SQL Guard │ ───▶ │  3. Execute (SQLite)│
 │  (Claude API)    │      │ SELECT-only,  │      │  read-only, capped  │
 │                  │      │ single stmt   │      │  row count           │
 └─────────────────┘      └──────────────┘      └─────────┬──────────┘
                                                            ▼
                                              ┌───────────────────────────┐
                                              │ 4. Results → Insight+Chart │
                                              │        (Claude API)        │
                                              └─────────────┬─────────────┘
                                                             ▼
                                                  chart + one-line takeaway
```

## Why it's built this way

**The SQL is never hidden.** Every answer shows the exact query that ran.
That's not just a UI choice — it's what makes the agent's reasoning
checkable instead of a black box, and it's the first thing worth pointing
to in a demo or a viva.

**The SQL is generated in one call and guarded before it runs.**
`core/services/sql_guard.py` rejects anything that isn't a single
read-only `SELECT` — no `DROP`, `DELETE`, `UPDATE`, `ATTACH`, multiple
chained statements, etc. — *before* it ever reaches the database. An LLM
generating SQL from free-text input is a real injection surface even
when there's no malicious user involved; treating it that way is the
main engineering idea in this project.

**Insight generation is a separate call, grounded in the actual returned
rows** (not the model's guess about what the data probably looks like).
This keeps the written takeaway from being a hallucinated summary.

## Stack

| Layer | Tech |
|---|---|
| NL→SQL + insights | Claude API (`anthropic` Python SDK) |
| Backend | Django + Django REST Framework, SQLite |
| Data loading | pandas (CSV/XLSX → SQL table + schema inference) |
| Frontend | React + Vite, Recharts, Lucide icons |

## Project structure

```
backend/
  dataagent/          Django project (settings, urls)
  core/
    models.py          Dataset, QueryLog
    views.py            upload / chat / history endpoints
    services/
      llm_client.py      the two Claude API calls
      sql_guard.py        SELECT-only validation
      schema_utils.py     CSV/XLSX -> SQLite + schema description
frontend/
  src/App.jsx           chat UI (falls back to an offline demo dataset
                         if no backend is reachable — open it directly
                         with `npm run dev` to see it work with zero setup)
```

## Setup

**Backend**

```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then paste your Anthropic API key into it
python manage.py migrate
python manage.py runserver  # http://localhost:8000
```

Get an API key at https://platform.claude.com (new accounts get a small free
trial credit, no card required).

**No card / prefer a permanently free option?** Set `LLM_PROVIDER=gemini` and
`GEMINI_API_KEY=...` in `.env` instead (leave `ANTHROPIC_API_KEY` blank).
Google AI Studio (https://aistudio.google.com) gives a free, no-credit-card
API key with no expiry. Nothing else changes — same endpoints, same UI.

**Frontend**

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

The frontend auto-detects the backend: if `localhost:8000` is reachable
it switches to **Live** mode and queries your real uploaded dataset; if
not, it runs in **Demo** mode against a small built-in sales dataset so
the UI is fully explorable with no setup at all.

**Loading your own data:** `POST /api/datasets/upload` with a `file`
field (CSV or XLSX) and an optional `name`. The response includes the
`dataset_id` the frontend needs.

## Deploying it

**Backend → Render**
1. Push this repo to GitHub.
2. Render dashboard → New → Blueprint → point it at the repo (`render.yaml`
   at the root configures the service) — or New → Web Service with root
   directory `backend`, build command `pip install -r requirements.txt`,
   start command from `backend/Procfile`.
3. Set the `ANTHROPIC_API_KEY` env var (and `CORS_ALLOWED_ORIGINS` once you
   have the Vercel URL from the next step).
4. Note: SQLite on Render's free tier is ephemeral — it resets on every
   redeploy. Fine for a portfolio demo; for anything persistent, swap in
   Render's free Postgres and point `DATABASES` at it.

**Frontend → Vercel**
1. New Project → same GitHub repo → set root directory to `frontend`.
2. Framework preset: Vite. Build command `npm run build`, output `dist`.
3. Env var `VITE_API_BASE` = your Render URL (e.g. `https://data-chat-agent-backend.onrender.com`).
4. Deploy, then go back to Render and set `CORS_ALLOWED_ORIGINS` to your
   new Vercel URL so the two can actually talk to each other.

## Safety note

This blocks destructive SQL and caps result size, which is the right
baseline for a tool that lets an LLM write queries against your data —
but it's a course project, not a hardened multi-tenant service. Don't
point it at a database you care about without adding authentication,
per-user data isolation, and rate limiting first.

## Taking this further

- Swap the demo's keyword-matched local agent for a second dataset type
  (e.g. a real Postgres connection) to show multi-source support
- Add a lightweight anomaly/outlier pass (z-score flagging) or a simple
  forecast (moving average / linear regression) as a third automatic
  insight type — ties in ML/DL fundamentals without much extra surface
- Streaming responses (Claude's streaming API) instead of a single
  blocking call, so the SQL appears token-by-token like it does in the
  demo's simulated version
- Auth + per-user datasets for a genuinely multi-tenant deployment
