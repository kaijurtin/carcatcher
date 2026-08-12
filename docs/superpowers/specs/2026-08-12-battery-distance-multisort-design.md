# Design: Battery capacity column, multi-column sort, distance-to-home sort

Date: 2026-08-12

## Context

CarCatcher tracks VW ID.3/ID.4 listings scraped from AutoScout24 and VW.de. The
listings table (`frontend/src/components/ListingsTable.tsx`) supports single-column
sort and a manual per-listing tag. This adds three features:

1. A battery capacity column.
2. Sorting by more than one column at a time.
3. Sorting by geographic distance from a fixed home point (postal code 66663,
   Merzig) to each listing's location.

## 1. Battery capacity

Neither source exposes battery capacity as a structured field — it only appears
inside free-text trim/title strings, e.g. `"Pro 82 kWh"`, `"id-4-pro-82-kwh"`.

- Add `battery_kwh: float | None` to `RawListing`, `Listing` (DB model), and
  `ListingRead` (API schema).
- Parse it via regex against `trim` (falling back to `title`) at parse time in
  each source's parser: pattern matches `NN` or `NN,N`/`NN.N` immediately
  followed by optional whitespace and `kWh` (case-insensitive), e.g.
  `re.compile(r"(\d+(?:[.,]\d+)?)\s*kWh", re.IGNORECASE)`. Comma is normalized to
  a dot before `float()`.
- If no match, `battery_kwh` is `None` — rendered as `—` in the table, sorts last
  (consistent with existing null handling for other numeric columns).
- New "Battery" column in `ListingsTable`, sortable, rendered as `82 kWh`.

## 2. Geographic distance from home

### Storage

- Add `latitude: float | None` and `longitude: float | None` to the `Listing` DB
  model (backfilled via the existing `_ADDED_COLUMNS` pattern in
  `db/engine.py`, same mechanism used for `tag`).
- `distance_km` is **not stored**. It's computed on read, in the API layer, from
  `listing.latitude`/`longitude` against a fixed home point, via the Haversine
  formula. This keeps it always consistent with the home point and avoids a
  stale cached value if the home point ever changes.

### Home point

- Hardcoded constants in `config.py`:
  `home_latitude: float = 49.4465237`, `home_longitude: float = 6.6269649`
  (Nominatim's centroid for German postal code 66663 / Merzig, verified live
  during design).
- Not user-configurable for now (YAGNI) — revisit as an env var if the home
  point ever needs to change.

### Geocoding

- New module `carcatcher/geocoding.py` wrapping Nominatim
  (`https://nominatim.openstreetmap.org/search`), queried as
  `f"{location}, Germany"`, with a descriptive `User-Agent` header (required by
  Nominatim's usage policy). Returns `(lat, lon) | None`; catches request
  errors/timeouts and empty results, returning `None` rather than raising —
  geocoding failures must never fail a crawl.
- Verified live against real listing location shapes from both sources:
  zip+city (`"24941 Flensburg"`, AutoScout24 shape) and city-only
  (`"Kölln-Reisiek"`, VW.de shape) both resolve correctly.
- Hook into `crawl.py`, after `_upsert`: if the upserted listing has no
  coordinates yet and `raw.location` is set, resolve coordinates via an
  in-crawl cache keyed by the raw `location` string. The cache is seeded from
  already-geocoded rows in the DB (distinct `location` → `(latitude,
  longitude)` for rows where both are non-null) so a city seen on a prior crawl
  is never re-geocoded. Only a genuine cache miss calls Nominatim, with a 1
  request/second delay between live calls (Nominatim's rate limit).
- Tradeoff (documented, accepted): the first crawl after this ships pays one
  Nominatim lookup per distinct unfamiliar city — for ~40 distinct cities
  that's ~40s added to that one `/refresh` call. Every subsequent crawl only
  geocodes genuinely new cities, so it's fast again. `/refresh` is already
  synchronous today (2 sources × 2 models, no AI calls) — this doesn't change
  that architecture, just the potential duration of the first call.

### API

- `ListingRead` gains `battery_kwh: float | None` and `distance_km: float | None`
  (the latter computed at serialization time, not from a DB column).

### Frontend

- New "Distance" column, sortable like other numeric columns, rendered as
  `12 km` or `—` when a listing has no coordinates yet (not yet geocoded, or
  geocoding failed).

## 3. Multi-column sort

Frontend-only change, entirely within `ListingsTable.tsx`.

- `SortState` (currently a single `{ field, direction }`) becomes
  `SortState[]` — an ordered list, most-significant key first.
- **Click** a header: replaces the entire sort with that column alone,
  toggling direction on repeat click of the same column. (Today's behavior,
  unchanged.)
- **Shift+click** a header:
  - If the column isn't already an active sort key, appends it to the end of
    the chain as the next tiebreaker (ascending).
  - If the column is already an active sort key, toggles its direction in
    place (position in the chain unchanged).
  - Shift+click never removes a column from the chain — to reset back to a
    single key, plain-click any header.
- Header UI: when more than one sort key is active, each active header shows a
  small rank badge (①/②/③) alongside its direction arrow, so primary vs.
  tiebreaker columns are visually distinguishable. With exactly one active key,
  the badge is omitted (matches today's look).
- `sortListings`/`compareValues`: the comparator iterates the sort key list in
  order, falling through to the next key when the current one compares equal
  (returns `0`), consistent with existing null-handling (nulls sort last
  regardless of direction) applied per key.

## Testing

- Backend: unit tests for the `battery_kwh` regex (both parsers, comma and dot
  decimal separators, no-match case), `geocoding.py` (mocked HTTP, cache-hit
  vs. cache-miss, failure-returns-None), and the `distance_km` Haversine
  computation in the API layer (known-distance fixture).
- Frontend: unit tests for multi-key `sortListings`/`compareValues` (tie
  fall-through, null handling per key) and shift+click header interaction
  (append, toggle-direction-in-place, replace-on-plain-click).

## Out of scope

- Configurable home point (env var) — revisit if it's ever needed.
- Manual battery-capacity override for listings the regex can't parse.
- Removing a single column from an active multi-sort chain without resetting
  the whole thing.
