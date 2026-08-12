# CarCatcher

A personal used-car finder for the German market. CarCatcher scrapes VW ID.3 and
ID.4 listings from a couple of official sources, normalizes them into one unified
table, and shows them on a single page — filterable by price, mileage, and trim,
refreshed on demand via a button. No AI, no scheduler, no saved searches: just a
current snapshot of what's on the market right now.

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI · Python 3.12+ · uv · pydantic-settings · SQLModel/SQLite · httpx · BeautifulSoup |
| Frontend | React · TypeScript · Vite · Tailwind v4 |
| Deploy | Proxmox LXC → Docker Compose (`api` + `ui`) → shared nginx → Cloudflare Tunnel (`carcatcher.jurtin.de`) |

## Layout

```
backend/    FastAPI app (carcatcher package) + pytest
frontend/   React + Vite SPA, served by nginx in prod
deploy/     Proxmox watchdog + sqlite backup scripts
docker-compose.yml   api + ui
```

## Data sources

- **AutoScout24** (`carcatcher/scraping/autoscout24.py`) — plain HTTP GET against
  AutoScout24's search pages; results are parsed out of the embedded Next.js
  `__NEXT_DATA__` JSON blob.
- **VW.de** (`carcatcher/scraping/vwde.py`) — Volkswagen's own official
  used/new-car search, called directly via the JSON API the site's own React app
  uses.
- **mobile.de** is deferred: live testing found it blocked by DataDome anti-bot
  protection even via headless Chromium with stealth evasions. Not implemented.

## API

- `GET /api/listings?model=id3|id4&max_price=&max_km=&trim=&source=&status=` —
  filtered listing rows (defaults to `status=active`).
- `POST /api/refresh` — synchronously runs both scrapers across both models,
  upserts into the `Listing` table, geocodes each new/changed listing location
  via the free Nominatim (OpenStreetMap) API (rate-limited to 1 request/second,
  capped per crawl — see `MAX_GEOCODES_PER_CRAWL` in `carcatcher/crawl.py`, so a
  refresh with many unfamiliar cities may take a bit longer and finish
  geocoding the rest on a later refresh), marks listings that disappeared as
  `gone`, and returns `{added, updated, gone, failed_sources, refreshed_at}`.
- `GET /api/health` — health check.

## Development

Run locally with Docker Compose (matches production):

```bash
cp .env.example .env   # fill in DATA_DIR / UI_PORT if needed
docker compose up --build
# ui:  http://localhost:${UI_PORT:-8080}
# api: proxied by the ui container at /api
```

Or run each side directly:

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

Copy `.env.example` to `.env` and fill in values. Vars: `APP_NAME`,
`DATABASE_PATH` (SQLite file path inside the api container), `DATA_DIR` (host
directory bind-mounted to `/data`), `UI_PORT` (port the ui/nginx container
exposes on the host).

## Deployment

Runs as an unprivileged Debian LXC on Proxmox with Docker Compose inside,
exposed via the shared nginx reverse proxy and Cloudflare Tunnel. See
`deploy/proxmox/`. Tables are created on startup if missing
(`SQLModel.metadata.create_all`); there is no general schema migration
tooling, but new nullable columns added to an existing table (e.g. `tag`,
`battery_kwh`, `latitude`, `longitude`) are non-destructively backfilled at
startup via `_ADDED_COLUMNS` in `carcatcher/db/engine.py`. A structural change
beyond adding a nullable column (renaming/dropping a column, changing a type)
still has no tooling and needs the SQLite file handled manually.

```bash
git pull && docker compose up --build -d
```
