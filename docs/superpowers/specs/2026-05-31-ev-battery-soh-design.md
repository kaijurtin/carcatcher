# Design: Battery capacity + State of Health (SoH) for EVs

**Date:** 2026-05-31
**Status:** Approved — ready for implementation plan
**Scope:** Add two EV-specific attributes (battery capacity in kWh, battery State of Health in %) to the full CarCatcher pipeline: extraction → storage → filtering → AI deal scoring → display.

## Background

CarCatcher normalizes German car classifieds (Kleinanzeigen, AutoScout24, mobile.de) via Haiku, stores them, and scores deals via a statistical fair-price baseline plus a Sonnet qualitative verdict. The `Listing` model has a `fuel` enum that already includes `electric`, but no battery-specific fields. Saved searches (e.g. VW ID.4) are EV-heavy, so buyers need to filter and judge cars by battery size and battery health.

Real-world data reality:
- **Battery capacity (kWh)** is commonly stated — it's a model spec.
- **State of Health (%)** is rarely published and, when present, lives in free text and is self-reported. The design must treat SoH as usually-missing and never penalize its absence.

## Goals

1. Capture `battery_kwh` and `battery_soh_pct` for electric (and plug-in hybrid) listings when present.
2. Let users filter / save searches by minimum battery capacity and minimum SoH.
3. Have the AI deal-scoring verdict reason about battery health for EVs.
4. Display both attributes in the listings table and detail drawer.

## Non-Goals (YAGNI)

- Battery-aware comparable matching (Approach B) — deferred until EV crawl volume is denser; current fair-price baseline is already sparsity-starved.
- SoH-adjusted price modelling (Approach C) — no depreciation data available.
- Charging specs (AC/DC power, connector type, range in km) — not requested.

## Chosen Approach: A — Prompt-context enrichment

Battery size + SoH are two new normalized fields, extracted for EVs, displayed, and filterable. For scoring they are injected into the Sonnet evaluation prompt so the qualitative verdict reasons about them; the **statistical fair-price baseline is unchanged**. Robust when data is sparse, and does not narrow the already-starved comparable matching.

## Detailed Design

### 1. Data model — `backend/carcatcher/db/models.py`

Two new nullable columns on `Listing`, placed alongside `power_kw` / `fuel`:

- `battery_kwh` — `Float`, nullable. Nominal usable battery capacity (e.g. 52.0, 58.0, 62.5, 77.0). `Float` because listings quote fractional values.
- `battery_soh_pct` — `Integer`, nullable. State of Health, 0–100.

Both remain `NULL` for non-EVs and whenever the seller does not state them. No new index initially — `battery_kwh_min` / `soh_min` filters run against an already make/model-scoped result set. An Alembic migration adds the two columns.

### 2. Normalization (Haiku extraction)

**`backend/carcatcher/normalization/schema.py`** — add both fields to `NormalizedListing`:
- `battery_soh_pct` validator: coerce values outside 0–100 → `None`.
- `battery_kwh` validator: sanity-bound to roughly 10–250 kWh; junk → `None`.
- Both default to `None`.

**`backend/carcatcher/normalization/prompts.py`** — extend `NORMALIZATION_SYSTEM`:
- Extract battery fields **only for electric / plug-in hybrid** listings.
- German term mapping:
  - `Akkukapazität`, `Batteriekapazität`, "… kWh" (capacity context) → `battery_kwh`
  - `SoH`, `State of Health`, `Batteriezustand`, `Akku-Gesundheit`, `Batteriegesundheit` → `battery_soh_pct`
- **Explicit guard:** `Reichweite` (range in km) is NOT battery capacity — the most likely extraction mistake. Likewise km/Wh consumption figures are not capacity.
- Conservative: return `null` when absent; never infer capacity from the model name.

### 3. Filtering — `StructuredFilters`

Add two fields in both definitions:
- Backend `backend/carcatcher/schemas.py`: `battery_kwh_min: float | None = None`, `soh_min: int | None = None`
- Frontend `frontend/src/types/index.ts`: `battery_kwh_min?: number | null;`, `soh_min?: number | null;`

Applied as SQL predicates `battery_kwh >= :battery_kwh_min` and `battery_soh_pct >= :soh_min` wherever `StructuredFilters` is translated into a query — both the NL-search path and the saved-search candidate selection.

The NL-search Sonnet parser prompt gains these fields so a query like *"ID.4 with at least 90% battery health"* maps to `soh_min=90`, and *"ID.4 Pro, min 77 kWh"* maps to `battery_kwh_min=77`.

### 4. AI deal scoring (Approach A)

Fair-price statistical baseline and comparable matching unchanged. The Sonnet evaluation prompt, for EV listings, receives `battery_kwh` and `battery_soh_pct` in its context with guidance:
- Low or clearly declining SoH → red flag, pushes the verdict toward "overpriced".
- Healthy SoH → supports a "good" verdict.
- Missing SoH → note as unknown; do **not** penalize.

### 5. Frontend display

- `frontend/src/components/ListingsTable.tsx`: append battery info to the spec line for EVs when present, e.g. `77 kWh · SoH 92%` (each segment shown only if its value exists).
- `frontend/src/components/ListingDetailDrawer.tsx`: add two SpecGrid cells — "Battery" (`battery_kwh` + " kWh") and "SoH" (`battery_soh_pct` + " %") — each rendered only when its value is non-null.

### 6. Testing (target 80% coverage)

Backend:
- Normalization: battery + SoH extracted from representative EV listings; the `Reichweite`-≠-capacity trap returns `null` capacity; non-EV listings yield `null` for both.
- Schema validators: out-of-range SoH and junk capacity coerce to `None`.
- Filters: `battery_kwh_min` / `soh_min` produce the correct SQL predicates and exclude/include listings as expected (including NULL-handling — NULL battery rows excluded when a min is set).
- Scoring: EV evaluation prompt includes battery fields when present; absence handled gracefully.

Frontend:
- Type additions compile; table/drawer render battery + SoH only when present, omit cleanly when null.

## Naming decisions (locked)

- `battery_kwh` (not `battery_capacity_kwh`) — matches the terse `power_kw` / `mileage_km` convention.
- `battery_soh_pct` stored as a plain integer percent.
- Filters: `battery_kwh_min`, `soh_min`.

## Data flow

```
raw HTML → Haiku (extract battery_kwh, battery_soh_pct for EVs)
        → NormalizedListing (validated)
        → Listing row (new columns)
        → StructuredFilters query (battery_kwh_min, soh_min predicates)
        → Sonnet deal scoring (battery health in prompt context)
        → Frontend (spec line + SpecGrid cells)
```

## Migration / deploy notes

- Alembic migration adds `battery_kwh` and `battery_soh_pct` columns (both nullable; safe on the existing populated table — no backfill required, existing rows stay NULL until re-normalized).
- No destructive data change; deploy follows the standard CT 113 migrate-then-restart flow.
