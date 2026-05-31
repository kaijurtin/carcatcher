# CarCatcher

A personal used-car finder for the German market. CarCatcher crawls listing sites
in the background, normalizes messy listings into clean structured data with Claude,
scores deals against a statistical fair-price baseline, supports structured and
natural-language search, and produces a reasoned cross-candidate recommendation
over a shortlist.

> Personal, single-user tool. Value priority: **Aggregation > Comparison > Deal
> scoring**. Data is a current snapshot only (no price history).

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI · Python 3.12+ · uv · pydantic-settings · SQLModel/SQLite · APScheduler |
| AI | Anthropic Claude (Haiku normalize · Sonnet evaluate · Opus recommend) |
| Scraping | Self-hosted Firecrawl behind a pluggable `Scraper` interface |
| Frontend | React · TypeScript · Vite · Tailwind v4 · Recharts |
| Deploy | Proxmox LXC → Docker Compose → nginx → Cloudflare Tunnel (`carcatcher.jurtin.de`) |

## Layout

```
backend/    FastAPI app (carcatcher package) + pytest
frontend/   React + Vite SPA, served by nginx in prod
deploy/     Proxmox watchdog + sqlite backup scripts
docker-compose.yml   api + ui + firecrawl
```

## Development

```bash
# Backend
cd backend
uv sync
uv run uvicorn carcatcher.main:app --reload   # http://localhost:8000
uv run pytest

# Frontend
cd frontend
npm install
npm run dev                                    # http://localhost:5173 (proxies /api)
npm run test
npm run build
```

## Configuration

Copy `.env.example` to `.env` and fill in values (see the file for the full list).
Key vars: `ANTHROPIC_API_KEY`, `FIRECRAWL_BASE_URL`, `DATABASE_PATH`,
`CRON_SCHEDULE`, `CRON_SECRET`, `AI_MONTHLY_BUDGET_USD`.

## Deployment

Runs as an unprivileged Debian LXC on Proxmox with Docker Compose inside, exposed
via the shared nginx reverse proxy and Cloudflare Tunnel. See `deploy/proxmox/`.

```bash
git pull && docker compose up --build -d
```
