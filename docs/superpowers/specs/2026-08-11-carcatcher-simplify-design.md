# CarCatcher Simplification — Design

**Date:** 2026-08-11
**Status:** Approved, pending implementation plan

## Why

CarCatcher grew into a full AI-assisted car-buying assistant (multi-source scraping via
Firecrawl, Claude/Ollama normalization, statistical + AI deal scoring, saved searches,
shortlists, model guides, NL search, cross-candidate recommendation — ~9,000 lines). That's
more than what's actually needed. The real want is much narrower: **a single table showing
up-to-date VW ID.3 / ID.4 offers from a few official sites, in a unified format, refreshed
on demand, filterable by price/km/trim.** This spec cuts the app down to that.

## Scope

**In scope:**
- Scrape 3 sources: mobile.de, AutoScout24, VW.de ("Das WeltAuto" / gebrauchtwagen.volkswagen.de)
- Models: VW ID.3 and ID.4 only — no other makes/models
- New and used listings both shown (condition is a column, not a filter in v1)
- One unified table, one page
- Manual refresh via a button — no background scheduler
- Filters: max price, max km, trim/description substring match (e.g. "Pro")
- No AI anywhere (no normalization, no scoring, no recommendation)

**Out of scope (deleted):** Kleinanzeigen source, saved searches, shortlists, model guides,
NL search, deal scoring, AI evaluation/recommendation, comparison charts, Firecrawl service.

## Architecture

Same repo, same deploy target (LXC + docker-compose on CT113, `carcatcher.jurtin.de`), same
two-container split (`api` uvicorn + `ui` nginx). The `firecrawl` service (redis + playwright +
api + worker) is removed from `docker-compose.yml` entirely — no longer needed.

Backend: FastAPI + SQLModel/SQLite, single `Listing` table, no APScheduler.
Frontend: React + Vite + Tailwind, single page (filter bar + table + refresh button).

## Data model

One table, `Listing`:

| field | type | notes |
|---|---|---|
| `id` | int | PK |
| `source` | str | `vw` \| `mobilede` \| `autoscout24` |
| `source_id` | str | site's own listing id |
| `url` | str | link to original listing |
| `model` | str | `id3` \| `id4` |
| `trim` | str | raw string from listing, e.g. "Pro", "GTX" — unnormalized |
| `price_eur` | int | |
| `mileage_km` | int \| null | |
| `year` | int \| null | first registration year |
| `power_kw` | int \| null | not all sites expose this cleanly |
| `condition` | str | `new` \| `used` |
| `location` | str \| null | |
| `title` | str | |
| `first_seen_at` | datetime | |
| `last_seen_at` | datetime | |
| `status` | str | `active` \| `gone` — set `gone` when a listing stops appearing in a refresh |

`UNIQUE(source, source_id)`. Refresh upserts on this key every run; no content-hash
idempotency check needed at this scale.

Dropped entirely: `SavedSearch`, `Shortlist`, `ShortlistItem`, `CrawlRun`, and all
`normalized_*` / `ai_evaluation` / `deal_score` / `comp_count` / `raw_html_hash` fields.

## Scraping strategy

Each source is one parser module with the same interface:
`fetch_listings(model: "id3" | "id4") -> list[RawListing]`. No AI step — each parser extracts
fields directly from what the site sends.

- **mobile.de** — known-good from a past session: HTTP GET with `ft=ELECTRICITY&ms=<make;;model>`,
  extract the page's embedded `window.__INITIAL_STATE__` JSON blob via `httpx` + regex/JSON
  parse. No browser needed.
- **AutoScout24** — narrows via URL path (`/lst/vw/id-4`). First implementation step: check
  whether the initial HTML embeds a data blob (e.g. `__NEXT_DATA__`-style) that plain HTTP can
  read. If the page is fully client-rendered, that one source needs a headless fetch.
- **VW.de (Das WeltAuto)** — new, unresearched. Same plan: try plain HTTP first, fall back to
  headless only if required.

**Accepted risk:** dropping Firecrawl means losing its built-in headless fallback. Default to
plain HTTP everywhere; reach for a single lightweight headless helper (bare Playwright, not the
Firecrawl service — no redis/worker/queue) only for whichever specific site(s) turn out to need
it. Determined as the first implementation step per site, before writing the rest of each parser.

## API surface

- `GET /api/listings?model=id3|id4|all&max_price=&max_km=&trim=&source=` — unified, filtered
  table rows
- `POST /api/refresh` — runs all 3 scrapers × 2 models, upserts into `Listing`, marks missing
  active listings `gone`, returns `{added, updated, gone, failed_sources}` + timestamp. If one
  source's parser fails, the others still complete; the failure is reported, not raised as a
  500.
- `GET /api/health` — unchanged

Removed: `/api/recommend`, `/api/saved-searches/*`, `/api/search` (NL search), `/api/models`
(model guides), AI-related parts of `/api/settings`.

## Frontend

Single page, replacing the current Dashboard / Model Guides / Saved Searches tabs:

- Filter bar: model toggle (ID.3 / ID.4 / both), max price, max km, trim text filter, source
  filter
- "Update search" button → `POST /api/refresh`, loading state, refetch `/api/listings` on
  completion; last-refreshed timestamp shown next to it
- Table columns: Model, Trim, Price, KM, Year, Power (kW), Condition, Location, Source, link
  out to the original listing

Removed: `ModelGuides`, `SavedSearches` pages; `ListingDetailDrawer`, `RecommendationPanel`,
`DealScoreBadge`, `AiToggle`, `SearchBar` (NL input) components.

## Deletion list

**Backend:** `carcatcher/ai/`, `carcatcher/scoring/`, `carcatcher/normalization/`,
`carcatcher/research/`, `carcatcher/scheduler/`, routes `recommend.py`, `saved_searches.py`,
`search.py`, AI parts of `settings.py`, `backend/model_guides/`. Kept/rewritten: `health.py`,
`listings.py`, `refresh.py`.

**Frontend:** the pages/components listed above, plus their tests.

**Infra:** `firecrawl` service block removed from `docker-compose.yml`. `.env.example` loses
`ANTHROPIC_API_KEY`, `OLLAMA_*`, `FIRECRAWL_BASE_URL`, `CRON_*`, `AI_MONTHLY_BUDGET_USD`.

## Deployment / migration

Same LXC/docker-compose deploy on CT113. Old data (AI evaluations, deal scores, non-ID.3/4
listings, saved searches) isn't useful going forward — **the SQLite DB is dropped and
recreated with the new schema on deploy**, no migration of old rows. Confirmed acceptable by
user (2026-08-11); no backup requested.

## Testing

- **Backend:** one fixture-based test per parser (saved sample HTML/JSON per site, following
  the existing Kleinanzeigen fixture pattern) covering happy-path extraction and a listing
  going `gone`. API tests for `/api/listings` filters and `/api/refresh`, including the
  partial-failure case.
- **Frontend:** table renders rows from a mocked API response; filter inputs affect the query;
  refresh button shows loading state and refetches. Reuses the existing Vitest/RTL setup.

## Open questions for implementation

- Whether AutoScout24 and VW.de need headless rendering — resolved by direct inspection as the
  first implementation step, not assumed here.
- Whether `POST /api/refresh` runs synchronously or as a background task — decided once real
  parser run-time is known (if a full 3-source × 2-model crawl is slow, use a background task
  with a status poll; otherwise keep it synchronous for simplicity).
