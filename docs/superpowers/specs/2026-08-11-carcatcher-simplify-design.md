# CarCatcher Simplification — Design

**Date:** 2026-08-11 (updated same day after live scraping research)
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
- Scrape 2 sources for v1: **VW.de** (Volkswagen's own official used/new-car search) and
  **AutoScout24**. mobile.de is deferred — see "mobile.de deferred" below.
- Models: VW ID.3 and ID.4 only — no other makes/models
- New and used listings both shown (condition is a column, not a filter in v1)
- One unified table, one page
- Manual refresh via a button — no background scheduler
- Filters: max price, max km, trim/description substring match (e.g. "Pro")
- No AI anywhere (no normalization, no scoring, no recommendation)

**Out of scope (deleted):** Kleinanzeigen source, saved searches, shortlists, model guides,
NL search, deal scoring, AI evaluation/recommendation, comparison charts, Firecrawl service.

**mobile.de deferred:** live testing (2026-08-11) confirmed mobile.de is blocked by DataDome
anti-bot protection even via headless Chromium with basic stealth evasions (plain `httpx` gets
a `403`; Playwright + `navigator.webdriver` override + custom UA still gets "Zugriff
verweigert"). Getting past it needs either a paid anti-bot/unblocking service or keeping some
flavor of the old Firecrawl setup — both against this spec's simplification goal. User decision
(2026-08-11): ship v1 with VW.de + AutoScout24 only; revisit mobile.de later as an isolated
add-on if still wanted, once a source is added its parser slots into the same `Parser`
interface without touching the other two.

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
| `source` | str | `vw` \| `autoscout24` (v1) — `mobilede` reserved for later |
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

Both v1 sources are confirmed (live-tested 2026-08-11) to work over **plain HTTP, no browser, no
rendering** — simpler than the original design assumed. Each source is one parser module with
the same interface: `fetch_listings(model: "id3" | "id4") -> list[RawListing]`. No AI step —
each parser extracts fields directly from what the site sends.

- **AutoScout24** — `GET https://www.autoscout24.de/lst/volkswagen/id-4?atype=C&cy=D&sort=standard&desc=0&page=N&size=20`
  (swap `id-4`/`id-3` in the path for the other model). Response HTML embeds a
  `<script id="__NEXT_DATA__" type="application/json">` tag; parse with
  `BeautifulSoup.find("script", id="__NEXT_DATA__")` → `json.loads` →
  `props.pageProps.listings`. This is exactly the existing
  `backend/carcatcher/scraping/autoscout24.py` parsing logic — kept as-is, just switched from a
  Firecrawl-fetched HTML string to a plain `httpx.get()` response body.
- **VW.de** — not the marketing site's HTML at all; the actual data comes from a JSON API the
  page's React app calls: `GET https://v3-120-0.gsl.feature-app.io/bff/car/search` with query
  params `t_manuf=BQ` (Volkswagen), `t_model=BQIE` (ID.4) or `t_model=BQID` (ID.3),
  `sort=DATE_OFFER&sortdirection=DESC&pageitems=12&page=N&country=DE&language=de&market=passenger`,
  plus three static credential params that were verified to work from a fresh, cookie-less
  `curl` process (i.e. they're not session-bound): `oneapiKey=nOqkwPxxu8ViK9aaHvTkglzVZAlX4yIx`,
  `dataVersion=B62F538267A27D9C9B1AC0E02FF3688F`, and
  `endpoint={"endpoint":{"type":"publish","country":"de","language":"de","content":"onehub_pkw","envName":"prod","testScenarioId":null},"signature":"eXxF3Vp4siIxU67pK2Vs14eGqdMbD0HzeFcn3b058j8="}`
  (URL-encoded). Response is `{"cars": [...], "meta": {"resultNumber": int, "pageMax": int}}`;
  `pageItems` is server-capped at 12 regardless of the requested value, so pagination loops
  `page=1..meta.pageMax`. Each car record has (verified against a live sample): `carid` (str,
  unique id), `subtitle.value` (str, full trim description e.g. "ID.4 Pro 210 kW IQ.LED AHK KAM
  WÄPU AR-HuD H/K"), `mileage.raw_value` (int), `initialreg` (ISO datetime, e.g.
  `"2025-12-09T00:00:00Z"` → take the year), `parsedPrice.value` (int, gross EUR), `powerLabel`
  (str, e.g. `" 85 kW (116 PS)"` → regex `r"(\d+)\s*kW"`), `cartype.code` (`"N"` = Neuwagen/new,
  `"Y"`/`"U"` = used variants → map to `condition`), `dealer.city.value` (str, location), `title`
  (str). Omitting `t_cartype` from the query returns both new and used together, which is what
  v1 wants. These static credentials are scoped to the current page-config version
  (`dataVersion`) and could rotate if VW redeploys their site; the parser should raise a clear
  error (not a silent empty result) on an unexpected response shape so a credential rotation is
  obvious rather than silently returning zero listings.

No headless browser, no Firecrawl, no `playwright` dependency needed for v1's two sources.

## API surface

- `GET /api/listings?model=id3|id4|all&max_price=&max_km=&trim=&source=` — unified, filtered
  table rows
- `POST /api/refresh` — runs both scrapers × 2 models (4 fetch loops total) **synchronously**
  (no background task/polling — 4 plain HTTP-based crawls with no AI calls should complete in
  well under the time an HTTP request can hold open), upserts into `Listing`, marks missing
  active listings `gone`, returns `{added, updated, gone, failed_sources}` + timestamp directly
  in the response. If one source's parser fails, the other still completes; the failure is
  reported in `failed_sources`, not raised as a 500.
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
`carcatcher/research/`, `carcatcher/scheduler/`, `carcatcher/pipeline/` (rebuilt much smaller,
see plan), routes `recommend.py`, `saved_searches.py`, `search.py`, AI parts of `settings.py`,
`backend/model_guides/`, `carcatcher/scraping/kleinanzeigen.py`,
`carcatcher/scraping/mobilede.py` (deferred with the source, see above),
`carcatcher/scraping/firecrawl_client.py`. Kept/rewritten: `health.py`, `listings.py`,
`refresh.py`, `scraping/autoscout24.py` (parsing logic reused, fetch mechanism swapped to plain
`httpx`). New: `scraping/vwde.py`.

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

