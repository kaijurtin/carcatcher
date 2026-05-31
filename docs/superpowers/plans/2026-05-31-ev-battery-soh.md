# EV Battery Capacity + SoH Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two EV-specific attributes — battery capacity (`battery_kwh`) and State of Health (`battery_soh_pct`) — through the full CarCatcher pipeline: Haiku extraction → storage → filtering → Sonnet deal scoring → frontend display.

**Architecture:** Two new nullable columns on `Listing`. Haiku extracts them for electric/hybrid listings only. They become filterable via `StructuredFilters` (`battery_kwh_min`, `soh_min`) on both the `/api/listings` route and the saved-search/NL-search query path. The Sonnet evaluation prompt receives them in context so the qualitative verdict reasons about battery health (Approach A — statistical fair-price baseline unchanged). Frontend shows them in the table spec line and detail drawer.

**Tech Stack:** Python 3 / FastAPI / SQLModel / Pydantic / pytest (backend); React + TypeScript + Tailwind (frontend); Anthropic SDK (Haiku normalization, Sonnet scoring).

**Spec:** `docs/superpowers/specs/2026-05-31-ev-battery-soh-design.md`

---

## File Map

**Backend (modify):**
- `backend/carcatcher/db/models.py` — add 2 columns to `Listing`
- `backend/carcatcher/normalization/schema.py` — add 2 fields + validators to `NormalizedListing`, add to `NORMALIZED_TOOL_SCHEMA`
- `backend/carcatcher/normalization/prompts.py` — extraction rules
- `backend/carcatcher/pipeline/normalize.py` — `_AI_FIELDS` mapping
- `backend/carcatcher/schemas.py` — `StructuredFilters` 2 fields
- `backend/carcatcher/queries.py` — `search_listings` WHERE clauses
- `backend/carcatcher/api/routes/listings.py` — query params, conditions, `ListingRead`
- `backend/carcatcher/ai/nl_search.py` — NL tool schema + prompt
- `backend/carcatcher/ai/evaluate.py` — `build_eval_input`
- `backend/carcatcher/ai/prompts.py` — `EVALUATION_SYSTEM`

**Backend (create):**
- `backend/tests/test_battery.py` — feature tests

**Frontend (modify):**
- `frontend/src/types/index.ts` — `Listing` + `StructuredFilters` interfaces
- `frontend/src/components/ListingsTable.tsx` — `specsLine`
- `frontend/src/components/ListingDetailDrawer.tsx` — `SpecGrid`

All backend tests run from `backend/` with `pytest -q` (asyncio_mode=auto, in-memory SQLite via `test_engine`/`client` fixtures in `backend/tests/conftest.py`).

---

## Task 1: Add columns + schema fields + validators

**Files:**
- Modify: `backend/carcatcher/db/models.py` (after line 94, `power_kw`)
- Modify: `backend/carcatcher/normalization/schema.py:16-30` (`NormalizedListing`)
- Test: `backend/tests/test_battery.py` (create)

- [ ] **Step 1: Write the failing validator test**

Create `backend/tests/test_battery.py`:

```python
"""Tests for EV battery capacity + State of Health feature."""

from __future__ import annotations

from carcatcher.normalization.schema import NormalizedListing


def test_battery_kwh_accepts_valid_capacity():
    norm = NormalizedListing(battery_kwh=77.0)
    assert norm.battery_kwh == 77.0


def test_battery_kwh_rejects_out_of_range():
    # 5 kWh is implausibly small, 500 kWh implausibly large -> coerced to None
    assert NormalizedListing(battery_kwh=5).battery_kwh is None
    assert NormalizedListing(battery_kwh=500).battery_kwh is None


def test_soh_pct_clamps_out_of_range_to_none():
    assert NormalizedListing(battery_soh_pct=92).battery_soh_pct == 92
    assert NormalizedListing(battery_soh_pct=150).battery_soh_pct is None
    assert NormalizedListing(battery_soh_pct=-3).battery_soh_pct is None


def test_battery_fields_default_none():
    norm = NormalizedListing()
    assert norm.battery_kwh is None
    assert norm.battery_soh_pct is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_battery.py -q`
Expected: FAIL — `NormalizedListing` has no `battery_kwh` / `battery_soh_pct`.

- [ ] **Step 3: Add columns to the `Listing` model**

In `backend/carcatcher/db/models.py`, immediately after line 94 (`power_kw: int | None = None`):

```python
    power_kw: int | None = None
    battery_kwh: float | None = None  # EV usable battery capacity (electric/hybrid only)
    battery_soh_pct: int | None = None  # EV battery State of Health 0-100
```

- [ ] **Step 4: Add fields + validators to `NormalizedListing`**

In `backend/carcatcher/normalization/schema.py`, add the two fields to the class body (after line 26, `power_kw`):

```python
    power_kw: int | None = None
    battery_kwh: float | None = None
    battery_soh_pct: int | None = None
```

Then add two validators after the existing `_v_seller` validator (after line 45):

```python
    @field_validator("battery_kwh")
    @classmethod
    def _v_battery_kwh(cls, v: float | None) -> float | None:
        if v is None:
            return None
        return v if 10 <= v <= 250 else None

    @field_validator("battery_soh_pct")
    @classmethod
    def _v_soh(cls, v: int | None) -> int | None:
        if v is None:
            return None
        return v if 0 <= v <= 100 else None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/test_battery.py -q`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/carcatcher/db/models.py backend/carcatcher/normalization/schema.py backend/tests/test_battery.py
git commit -m "feat: add battery_kwh + battery_soh_pct model fields and validators"
```

---

## Task 2: Haiku tool schema + extraction prompt

**Files:**
- Modify: `backend/carcatcher/normalization/schema.py:57-76` (`NORMALIZED_TOOL_SCHEMA`)
- Modify: `backend/carcatcher/normalization/prompts.py:3-29` (`NORMALIZATION_SYSTEM`)
- Test: `backend/tests/test_battery.py`

- [ ] **Step 1: Write the failing prompt-contract test**

Append to `backend/tests/test_battery.py`:

```python
from carcatcher.normalization.prompts import NORMALIZATION_SYSTEM
from carcatcher.normalization.schema import NORMALIZED_TOOL_SCHEMA


def test_tool_schema_exposes_battery_fields():
    props = NORMALIZED_TOOL_SCHEMA["properties"]
    assert "battery_kwh" in props
    assert "battery_soh_pct" in props


def test_prompt_mentions_battery_and_reichweite_guard():
    # Must instruct extraction and must warn that Reichweite (range) != capacity.
    assert "battery_kwh" in NORMALIZATION_SYSTEM
    assert "battery_soh_pct" in NORMALIZATION_SYSTEM
    assert "Reichweite" in NORMALIZATION_SYSTEM
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_battery.py -q`
Expected: FAIL — `battery_kwh` not in schema/prompt.

- [ ] **Step 3: Add fields to `NORMALIZED_TOOL_SCHEMA`**

In `backend/carcatcher/normalization/schema.py`, inside the `"properties"` dict (after the `power_kw` line, line 69):

```python
        "power_kw": {**_int(), "description": "Engine power in kW (convert from PS: kW≈PS*0.7355)"},
        "battery_kwh": {
            "type": ["number", "null"],
            "description": "EV usable battery capacity in kWh (electric/hybrid only). "
            "NOT the range in km (Reichweite). null if not stated.",
        },
        "battery_soh_pct": {
            **_int(),
            "description": "EV battery State of Health as a percent 0-100 "
            "(electric/hybrid only). null if not stated.",
        },
```

- [ ] **Step 4: Extend the extraction prompt**

In `backend/carcatcher/normalization/prompts.py`, add these bullets after the `power_kw` line (line 23), before the `body_type` bullet:

```python
- power_kw: engine power in kW. If only PS/HP given, convert: kW = round(PS * 0.7355).
- battery_kwh: ONLY for electric/hybrid cars. Usable battery capacity in kWh
  (e.g. "77 kWh", "Akkukapazität 58 kWh", "Batteriekapazität: 62"). IMPORTANT:
  "Reichweite" / range in km is NOT capacity — never put a km figure here. Energy
  consumption ("kWh/100km") is also NOT capacity. null if not clearly stated.
- battery_soh_pct: ONLY for electric/hybrid cars. Battery State of Health as a
  percent 0-100 (e.g. "SoH 92%", "Batteriezustand 95%", "Akku-Gesundheit: 88%").
  null if not stated. Never infer from age or mileage.
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/test_battery.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/carcatcher/normalization/schema.py backend/carcatcher/normalization/prompts.py backend/tests/test_battery.py
git commit -m "feat: extract battery capacity + SoH for EVs in Haiku normalization"
```

---

## Task 3: Persist battery fields onto the Listing row

**Files:**
- Modify: `backend/carcatcher/pipeline/normalize.py` (`_AI_FIELDS` tuple)
- Test: `backend/tests/test_battery.py`

- [ ] **Step 1: Write the failing mapping test**

Append to `backend/tests/test_battery.py`:

```python
from carcatcher.db.models import Listing
from carcatcher.pipeline.normalize import apply_normalized


def test_apply_normalized_copies_battery_fields():
    listing = Listing(source="kleinanzeigen", source_id="x1", url="http://x")
    norm = NormalizedListing(
        make="Volkswagen", model="ID.4", fuel="electric",
        battery_kwh=77.0, battery_soh_pct=94,
    )
    apply_normalized(listing, norm)
    assert listing.battery_kwh == 77.0
    assert listing.battery_soh_pct == 94


def test_apply_normalized_leaves_battery_none_for_non_ev():
    listing = Listing(source="kleinanzeigen", source_id="x2", url="http://x")
    norm = NormalizedListing(make="Volkswagen", model="Golf", fuel="diesel")
    apply_normalized(listing, norm)
    assert listing.battery_kwh is None
    assert listing.battery_soh_pct is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_battery.py -q`
Expected: FAIL — `listing.battery_kwh` stays `None` because the field is not in `_AI_FIELDS`.

- [ ] **Step 3: Add fields to `_AI_FIELDS`**

In `backend/carcatcher/pipeline/normalize.py`, find the `_AI_FIELDS` tuple and add the two fields:

```python
_AI_FIELDS = (
    "make",
    "model",
    "variant",
    "fuel",
    "transmission",
    "power_kw",
    "battery_kwh",
    "battery_soh_pct",
    "body_type",
    "location_city",
    "location_plz",
    "seller_type",
)
```

(`apply_normalized` only writes when the value is non-`None`, so non-EV listings — which extract `None` — leave the columns `NULL`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_battery.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/carcatcher/pipeline/normalize.py backend/tests/test_battery.py
git commit -m "feat: persist battery_kwh + battery_soh_pct from normalization"
```

---

## Task 4: Filtering — StructuredFilters, queries, API route, ListingRead

**Files:**
- Modify: `backend/carcatcher/schemas.py:8-26` (`StructuredFilters`)
- Modify: `backend/carcatcher/queries.py` (`search_listings` conditions)
- Modify: `backend/carcatcher/api/routes/listings.py` (`ListingRead`, params, conditions)
- Test: `backend/tests/test_battery.py`

- [ ] **Step 1: Write the failing filter tests**

Append to `backend/tests/test_battery.py`:

```python
from sqlmodel import Session

from carcatcher.db.engine import get_engine
from carcatcher.db.models import ListingStatus
from carcatcher.queries import search_listings
from carcatcher.schemas import StructuredFilters


def _seed_ev(s: Session) -> None:
    s.add(Listing(
        source="kleinanzeigen", source_id="ev-hi", url="http://hi",
        status=ListingStatus.ACTIVE.value, make="Volkswagen", model="ID.4",
        fuel="electric", battery_kwh=77.0, battery_soh_pct=95,
    ))
    s.add(Listing(
        source="kleinanzeigen", source_id="ev-lo", url="http://lo",
        status=ListingStatus.ACTIVE.value, make="Volkswagen", model="ID.4",
        fuel="electric", battery_kwh=52.0, battery_soh_pct=80,
    ))
    s.commit()


def test_search_filters_by_battery_kwh_min(test_engine):
    with Session(get_engine()) as s:
        _seed_ev(s)
        rows = search_listings(s, StructuredFilters(battery_kwh_min=70))
        assert {r.source_id for r in rows} == {"ev-hi"}


def test_search_filters_by_soh_min(test_engine):
    with Session(get_engine()) as s:
        _seed_ev(s)
        rows = search_listings(s, StructuredFilters(soh_min=90))
        assert {r.source_id for r in rows} == {"ev-hi"}


def test_listings_api_filters_by_soh_min(client):
    with Session(get_engine()) as s:
        _seed_ev(s)
    resp = client.get("/api/listings", params={"soh_min": 90})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["source_id"] == "ev-hi"
    # response model exposes the new fields
    assert body["items"][0]["battery_kwh"] == 77.0
    assert body["items"][0]["battery_soh_pct"] == 95
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_battery.py -q`
Expected: FAIL — `StructuredFilters` has no `battery_kwh_min`/`soh_min`; API has no such param; `battery_kwh` not in response.

- [ ] **Step 3: Add fields to backend `StructuredFilters`**

In `backend/carcatcher/schemas.py`, after line 25 (`radius_km`):

```python
    plz: str | None = None
    radius_km: int | None = None
    battery_kwh_min: float | None = None
    soh_min: int | None = None
    keywords: str | None = Field(default=None, description="Free-text fallback query")
```

- [ ] **Step 4: Add WHERE clauses to `search_listings`**

In `backend/carcatcher/queries.py`, after the `filters.mileage_max` block (and before the `filters.plz` block):

```python
    if filters.mileage_max is not None:
        conditions.append(Listing.mileage_km <= filters.mileage_max)
    if filters.battery_kwh_min is not None:
        conditions.append(Listing.battery_kwh >= filters.battery_kwh_min)
    if filters.soh_min is not None:
        conditions.append(Listing.battery_soh_pct >= filters.soh_min)
    if filters.plz:
        conditions.append(Listing.location_plz == filters.plz)
```

- [ ] **Step 5: Add params + conditions + response fields to the listings route**

In `backend/carcatcher/api/routes/listings.py`:

(a) Add to `ListingRead` after line 40 (`power_kw`):

```python
    power_kw: int | None
    battery_kwh: float | None
    battery_soh_pct: int | None
```

(b) Add query params to `list_listings` after line 88 (`mileage_max`):

```python
    mileage_max: int | None = None,
    battery_kwh_min: float | None = None,
    soh_min: int | None = None,
    deal_score_min: float | None = None,
```

(c) Add conditions after line 125 (the `mileage_max` block):

```python
    if mileage_max is not None:
        conditions.append(Listing.mileage_km <= mileage_max)
    if battery_kwh_min is not None:
        conditions.append(Listing.battery_kwh >= battery_kwh_min)
    if soh_min is not None:
        conditions.append(Listing.battery_soh_pct >= soh_min)
    if deal_score_min is not None:
        conditions.append(Listing.deal_score >= deal_score_min)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_battery.py -q`
Expected: PASS.

- [ ] **Step 7: Run the full backend suite (no regressions)**

Run: `cd backend && pytest -q`
Expected: all green (existing 91 + new battery tests).

- [ ] **Step 8: Commit**

```bash
git add backend/carcatcher/schemas.py backend/carcatcher/queries.py backend/carcatcher/api/routes/listings.py backend/tests/test_battery.py
git commit -m "feat: filter listings by battery_kwh_min and soh_min"
```

---

## Task 5: NL search translation of battery filters

**Files:**
- Modify: `backend/carcatcher/ai/nl_search.py` (`NL_SEARCH_SYSTEM`, `NL_SEARCH_TOOL_SCHEMA`)
- Test: `backend/tests/test_battery.py`

- [ ] **Step 1: Write the failing contract test**

Append to `backend/tests/test_battery.py`:

```python
from carcatcher.ai.nl_search import NL_SEARCH_SYSTEM, NL_SEARCH_TOOL_SCHEMA


def test_nl_tool_schema_has_battery_filters():
    props = NL_SEARCH_TOOL_SCHEMA["properties"]["filters"]["properties"]
    assert "battery_kwh_min" in props
    assert "soh_min" in props


def test_nl_prompt_mentions_battery_filters():
    assert "battery_kwh_min" in NL_SEARCH_SYSTEM
    assert "soh_min" in NL_SEARCH_SYSTEM
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_battery.py -q`
Expected: FAIL — keys absent.

- [ ] **Step 3: Add filter keys to `NL_SEARCH_TOOL_SCHEMA`**

In `backend/carcatcher/ai/nl_search.py`, inside `filters.properties` (after the `mileage_max` line):

```python
                "mileage_max": {"type": ["integer", "null"]},
                "battery_kwh_min": {"type": ["number", "null"]},
                "soh_min": {"type": ["integer", "null"]},
                "plz": {"type": ["string", "null"]},
```

- [ ] **Step 4: Add guidance to `NL_SEARCH_SYSTEM`**

Add this line to the "Filter rules" block (after the price/mileage/year line):

```python
- battery_kwh_min: for electric cars, a minimum usable battery capacity in kWh
  ("mindestens 77 kWh", "großer Akku"). soh_min: minimum battery State of Health
  percent ("Batteriegesundheit über 90%", "SoH >= 85"). Only set these for EV requests.
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/test_battery.py -q`
Expected: PASS.

- [ ] **Step 6: Verify the translated dict flows into StructuredFilters**

The NL result dict is unpacked into `StructuredFilters` downstream; since Task 4 added both fields to that model, the new keys propagate with no further change. Confirm by grepping for where `StructuredFilters(` is constructed from NL output:

Run: `cd backend && grep -rn "StructuredFilters(" carcatcher`
Expected: the NL-search consumer builds `StructuredFilters(**...)` (or `.model_validate`) — extra keys are accepted, new keys carried through. If it constructs field-by-field, add `battery_kwh_min=...` / `soh_min=...` there too.

- [ ] **Step 7: Commit**

```bash
git add backend/carcatcher/ai/nl_search.py backend/tests/test_battery.py
git commit -m "feat: translate battery/SoH constraints in NL search"
```

---

## Task 6: Battery health in Sonnet deal evaluation

**Files:**
- Modify: `backend/carcatcher/ai/evaluate.py:30-44` (`build_eval_input`)
- Modify: `backend/carcatcher/ai/prompts.py:3-26` (`EVALUATION_SYSTEM`)
- Test: `backend/tests/test_battery.py`

- [ ] **Step 1: Write the failing eval-context test**

Append to `backend/tests/test_battery.py`:

```python
from carcatcher.ai.evaluate import build_eval_input


def test_eval_input_includes_battery_for_ev():
    listing = Listing(
        source="k", source_id="e", url="http://e", fuel="electric",
        make="Volkswagen", model="ID.4", battery_kwh=77.0, battery_soh_pct=88,
    )
    text = build_eval_input(listing)
    assert "77" in text and "kWh" in text
    assert "88" in text  # SoH


def test_eval_input_omits_battery_for_non_ev():
    listing = Listing(
        source="k", source_id="d", url="http://d", fuel="diesel",
        make="Volkswagen", model="Golf",
    )
    text = build_eval_input(listing)
    assert "State of Health" not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_battery.py -q`
Expected: FAIL — battery line not in eval input.

- [ ] **Step 3: Add an EV battery line to `build_eval_input`**

In `backend/carcatcher/ai/evaluate.py`, inside `build_eval_input`, after the `specs = [...]` list is built (after the power/transmission entry) and before `desc = ...`, append a conditional battery line:

```python
    if listing.fuel in ("electric", "hybrid"):
        cap = f"{listing.battery_kwh} kWh" if listing.battery_kwh is not None else "capacity not stated"
        soh = (
            f"{listing.battery_soh_pct}%" if listing.battery_soh_pct is not None
            else "State of Health unknown"
        )
        specs.append(f"Battery: {cap} | State of Health: {soh}")
    desc = listing.raw_text.strip() or "(no description)"
```

- [ ] **Step 4: Add EV guidance to `EVALUATION_SYSTEM`**

In `backend/carcatcher/ai/prompts.py`, add to the "Guidance" block (after the `pros / cons` bullet):

```python
- For electric/hybrid cars: weigh battery State of Health (SoH) heavily. A low or
  clearly declining SoH is a major red flag and should push the verdict toward
  "overpriced" (battery replacement is expensive); a healthy SoH supports "good".
  Smaller battery capacity (kWh) means less range — note it as a con only if the
  asking price ignores it. If SoH is unknown, say so and treat it as a buyer
  check-item — do NOT penalize the verdict for missing data.
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/test_battery.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/carcatcher/ai/evaluate.py backend/carcatcher/ai/prompts.py backend/tests/test_battery.py
git commit -m "feat: factor EV battery health into Sonnet deal evaluation"
```

---

## Task 7: Frontend types

**Files:**
- Modify: `frontend/src/types/index.ts` (`Listing` + `StructuredFilters`)

- [ ] **Step 1: Add fields to the `Listing` interface**

In `frontend/src/types/index.ts`, after the `power_kw` line in `Listing`:

```typescript
  power_kw: number | null;
  battery_kwh: number | null;
  battery_soh_pct: number | null;
```

- [ ] **Step 2: Add fields to the `StructuredFilters` interface**

After the `mileage_max` line:

```typescript
  mileage_max?: number | null;
  battery_kwh_min?: number | null;
  soh_min?: number | null;
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat: add battery fields to frontend Listing + StructuredFilters types"
```

---

## Task 8: Frontend display (table spec line + detail drawer)

**Files:**
- Modify: `frontend/src/components/ListingsTable.tsx:20-32` (`specsLine`)
- Modify: `frontend/src/components/ListingDetailDrawer.tsx:100-122` (`SpecGrid`)

- [ ] **Step 1: Add battery segments to `specsLine`**

In `frontend/src/components/ListingsTable.tsx`, extend the `parts` array (after the `power_kw` entry):

```typescript
  const parts = [
    l.variant,
    l.fuel ? (FUEL_LABEL[l.fuel] ?? l.fuel) : null,
    l.transmission === "automatic"
      ? "Automatik"
      : l.transmission === "manual"
        ? "Schaltgetriebe"
        : null,
    l.power_kw ? `${l.power_kw} kW` : null,
    l.battery_kwh ? `${l.battery_kwh} kWh` : null,
    l.battery_soh_pct != null ? `SoH ${l.battery_soh_pct}%` : null,
  ].filter(Boolean);
```

- [ ] **Step 2: Add conditional rows to `SpecGrid`**

In `frontend/src/components/ListingDetailDrawer.tsx`, change the `rows` declaration so battery rows are appended only when present:

```typescript
  const rows: [string, string | JSX.Element][] = [
    ["Price", formatPrice(listing.price, listing.raw_price)],
    ["Deal", <DealScoreBadge key="d" listing={listing} />],
    ["Year", formatYear(listing.year)],
    ["Mileage", formatKm(listing.mileage_km)],
    ["Fuel", listing.fuel ?? "—"],
    ["Transmission", listing.transmission ?? "—"],
    ["Power", listing.power_kw ? `${listing.power_kw} kW` : "—"],
    ["Seller", listing.seller_type ?? "—"],
    ["Location", listing.location_raw ?? "—"],
  ];
  if (listing.battery_kwh != null) {
    rows.push(["Battery", `${listing.battery_kwh} kWh`]);
  }
  if (listing.battery_soh_pct != null) {
    rows.push(["SoH", `${listing.battery_soh_pct} %`]);
  }
```

- [ ] **Step 3: Typecheck + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: compiles, build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ListingsTable.tsx frontend/src/components/ListingDetailDrawer.tsx
git commit -m "feat: display battery capacity + SoH in listings table and detail drawer"
```

---

## Task 9: Production migration + deploy verification

The project has **no migration framework** — `SQLModel.metadata.create_all` (`backend/carcatcher/db/engine.py:45`) creates missing *tables* but never adds *columns* to an existing populated table. Fresh DBs and the pytest in-memory DB get the new columns automatically; the **production SQLite DB on CT 113 needs an explicit `ALTER TABLE`.**

- [ ] **Step 1: Deploy code to CT 113**

Pull/rebuild per the standard flow (the deploy that ships this branch):

```bash
# on CT 113, in /app
git pull && docker compose up -d --build
```

- [ ] **Step 2: Add the two columns to the production DB (idempotent)**

Run inside the api container — path-agnostic, uses the app's own engine:

```bash
docker compose exec api python -c "
from sqlalchemy import text
from carcatcher.db.engine import get_engine
eng = get_engine()
with eng.begin() as c:
    for ddl in (
        'ALTER TABLE listing ADD COLUMN battery_kwh FLOAT',
        'ALTER TABLE listing ADD COLUMN battery_soh_pct INTEGER',
    ):
        try:
            c.execute(text(ddl)); print('added:', ddl)
        except Exception as e:
            print('skip (already exists?):', e)
print('done')
"
```

Expected: `added: ...` on first run; `skip ...` if re-run (safe to repeat).

- [ ] **Step 3: Re-normalize EV listings so battery data populates**

Existing rows stay `NULL` until re-normalized. Trigger a crawl/normalize of an EV search (e.g. the ID.4 saved search) via the UI "Run now" button, or the manual crawl endpoint. Battery fields populate only where the source listing states them.

- [ ] **Step 4: Verify end-to-end**

```bash
# API exposes the fields and filters
curl -s "https://carcatcher.jurtin.de/api/listings?soh_min=80&page_size=3" \
  -H "User-Agent: Mozilla/5.0" | python -m json.tool | grep -E "battery_kwh|battery_soh_pct|total"
```

Expected: response items include `battery_kwh` / `battery_soh_pct` keys; filtered `total` reflects the SoH constraint. Then load the dashboard and confirm an EV listing shows battery/SoH in the spec line and detail drawer.

- [ ] **Step 5: Final commit (if any deploy-driven config changed)**

```bash
git add -A && git commit -m "chore: deploy EV battery + SoH to CT 113" || echo "nothing to commit"
```

---

## Notes for the implementer

- **DRY:** all SQL filtering of battery fields mirrors the existing `mileage_max` pattern in both `queries.py` and `listings.py` — keep them consistent.
- **YAGNI:** do NOT add battery capacity to the comparable-matching key or build an SoH price model (explicitly deferred in the spec — Approaches B/C).
- **Extraction reality:** SoH is usually absent in classifieds. Tests assert graceful `None` handling everywhere; never penalize missing SoH in scoring.
- **The Reichweite trap** (range in km mistaken for kWh capacity) is the single most likely extraction bug — the prompt guard in Task 2 and the validator bound (10–250 kWh) in Task 1 are both defenses; keep both.
