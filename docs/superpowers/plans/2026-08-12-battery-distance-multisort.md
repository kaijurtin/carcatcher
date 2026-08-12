# Battery Capacity, Multi-Column Sort, Distance-to-Home Sort Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a battery-capacity column, multi-column table sorting, and distance-from-home sorting to CarCatcher's listings table.

**Architecture:** Backend: parse battery capacity from free-text trim/title via regex at crawl time; geocode each listing's location string via the free Nominatim API (cached, rate-limited) and store lat/lon; compute distance-to-home on read via Haversine (never stored). Frontend: extend the `Listing` type and table with two new sortable columns, and generalize the table's single-column sort state into an ordered chain of sort keys driven by click (replace) vs. shift+click (append/toggle-in-place).

**Tech Stack:** FastAPI · SQLModel/SQLite · httpx · pytest · respx (backend) — React · TypeScript · Vitest · Testing Library (frontend).

## Global Constraints

- Design source: `docs/superpowers/specs/2026-08-12-battery-distance-multisort-design.md`.
- Battery capacity is parsed via regex from trim/title text (`NN[.,N] kWh`); no structured field exists on either source. `None` when unparseable.
- Geocoding uses Nominatim (`https://nominatim.openstreetmap.org/search`), throttled to 1 request/second, with a descriptive `User-Agent`. Geocoding failures return `None` and must never raise or fail a crawl.
- Home point is a hardcoded config constant: `home_latitude = 49.4465237`, `home_longitude = 6.6269649` (centroid of postal code 66663 / Merzig, verified live via Nominatim during design).
- `distance_km` is never persisted — always computed on read from `latitude`/`longitude` vs. the home constants.
- New DB columns (`battery_kwh`, `latitude`, `longitude`) must be backfilled onto an already-deployed SQLite file via the existing `_ADDED_COLUMNS` pattern in `carcatcher/db/engine.py` (same mechanism as `tag`).
- Multi-column sort: plain click replaces the whole sort chain with that column (toggling direction if it was already the sole active key); shift+click appends a column as a tiebreaker, or toggles its direction in place if already active. Shift+click never removes a column.
- Every task must leave the full test suite green — every `RawListing`/`AppState` construction site in the codebase must be updated in the same task that adds a new required field, not deferred to a later task.

---

### Task 1: Battery-capacity regex parser

**Files:**
- Create: `backend/carcatcher/scraping/battery.py`
- Test: `backend/tests/test_battery.py`

**Interfaces:**
- Produces: `parse_battery_kwh(*texts: str | None) -> float | None` — searches each text in order for the first `NN[.,N] kWh` match (case-insensitive), returns `None` if none match. Used by Task 2's parsers.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_battery.py
"""Tests for battery-capacity extraction from free-text trim/title strings."""

from __future__ import annotations

from carcatcher.scraping.battery import parse_battery_kwh


def test_parses_whole_number_kwh():
    assert parse_battery_kwh("Pro 82 kWh") == 82.0


def test_parses_comma_decimal_kwh():
    assert parse_battery_kwh("Pure 58,0 kWh Performance") == 58.0


def test_parses_dot_decimal_kwh():
    assert parse_battery_kwh("Pure 58.5 kWh") == 58.5


def test_is_case_insensitive():
    assert parse_battery_kwh("Pro 82 KWH") == 82.0


def test_returns_none_when_no_match_in_any_text():
    assert parse_battery_kwh("Pro Performance", "VW ID.4 Pro Performance") is None


def test_returns_none_for_none_and_empty_strings():
    assert parse_battery_kwh(None, "", None) is None


def test_uses_first_matching_text_in_order():
    assert parse_battery_kwh("Pure", "Pro 82 kWh") == 82.0


def test_prefers_first_text_over_second_when_both_match():
    assert parse_battery_kwh("Pro 58 kWh", "Pro 82 kWh") == 58.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_battery.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'carcatcher.scraping.battery'`

- [ ] **Step 3: Write the implementation**

```python
# backend/carcatcher/scraping/battery.py
"""Extracts battery capacity (kWh) embedded in free-text trim/title strings,
e.g. "Pro 82 kWh" — neither source exposes it as a structured field."""

from __future__ import annotations

import re

_BATTERY_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*kWh", re.IGNORECASE)


def parse_battery_kwh(*texts: str | None) -> float | None:
    """Return the first "NN[.,N] kWh" match found across `texts`, checked in
    order, or None if none of them contain one."""
    for text in texts:
        if not text:
            continue
        match = _BATTERY_RE.search(text)
        if match:
            return float(match.group(1).replace(",", "."))
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_battery.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/carcatcher/scraping/battery.py backend/tests/test_battery.py
git commit -m "feat: add battery-capacity regex parser"
```

---

### Task 2: Wire battery_kwh through RawListing and both parsers

**Files:**
- Modify: `backend/carcatcher/scraping/base.py`
- Modify: `backend/carcatcher/scraping/autoscout24.py`
- Modify: `backend/carcatcher/scraping/vwde.py`
- Modify: `backend/tests/test_autoscout24.py`
- Modify: `backend/tests/test_vwde.py`
- Modify: `backend/tests/test_crawl.py`
- Modify: `backend/tests/test_api_refresh.py`

**Interfaces:**
- Consumes: `parse_battery_kwh` from Task 1 (`carcatcher.scraping.battery`).
- Produces: `RawListing.battery_kwh: float | None` — required field every construction site must now supply. Consumed by Task 5 (`crawl.py`'s `_upsert`).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_autoscout24.py`:

```python
def test_battery_kwh_parsed_from_trim_when_present():
    listings = parse_search_html(_html(), "id4")
    battery_listing = next(l for l in listings if "82 kWh" in l.trim)
    assert battery_listing.battery_kwh == 82.0


def test_battery_kwh_is_none_when_trim_has_no_match():
    listings = parse_search_html(_html(), "id4")
    first = listings[0]
    assert first.battery_kwh is None
```

Append to `backend/tests/test_vwde.py`:

```python
def test_battery_kwh_parsed_from_subtitle_when_present():
    data = _data()
    data["cars"][0]["subtitle"]["value"] = "ID.4 Pro 77 kWh NAV"
    listings = parse_search_response(data, "id4")
    assert listings[0].battery_kwh == 77.0


def test_battery_kwh_is_none_when_no_kwh_mentioned():
    listings = parse_search_response(_data(), "id4")
    assert all(l.battery_kwh is None for l in listings)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_autoscout24.py tests/test_vwde.py -v`
Expected: FAIL — `TypeError: RawListing.__init__() missing 1 required positional argument: 'battery_kwh'` (the fixtures don't error yet since `RawListing` doesn't have the field; once you add it in Step 3 without updating callers, existing tests fail this way instead — see note below)

> Note: since `battery_kwh` doesn't exist on `RawListing` yet, the two new tests above will actually fail with `AttributeError: 'RawListing' object has no attribute 'battery_kwh'` at this point. That's the expected RED state — proceed to Step 3.

- [ ] **Step 3: Add the field and wire both parsers**

In `backend/carcatcher/scraping/base.py`, add `battery_kwh` to `RawListing` right after `power_kw`:

```python
@dataclass
class RawListing:
    """One listing, already in the shape `crawl.py` upserts into `Listing`."""

    source: str
    source_id: str
    url: str
    model: Model
    trim: str
    price_eur: int | None
    mileage_km: int | None
    year: int | None
    power_kw: int | None
    battery_kwh: float | None
    condition: str  # "new" | "used"
    location: str | None
    title: str
```

In `backend/carcatcher/scraping/autoscout24.py`, add the import:

```python
from carcatcher.scraping.battery import parse_battery_kwh
```

and replace `_item_to_listing` with:

```python
def _item_to_listing(item: dict, model: Model) -> RawListing | None:
    if not item.get("id"):
        return None
    vehicle = item.get("vehicle") or {}
    # AS24 can return off-model vehicles in unfiltered contexts (boosted/sponsored
    # slots) even when the search URL targets a specific model — guard against
    # storing them mislabeled as the requested VW ID.3/ID.4.
    if (vehicle.get("make") or "").strip().lower() != "volkswagen":
        return None
    if _normalize_model_code(vehicle.get("model")) != model:
        return None
    url = item.get("url") or ""
    url = url if url.startswith("http") else f"{BASE_URL}{url}"
    details = _details(item.get("vehicleDetails") or [])
    loc = item.get("location") or {}
    trim = vehicle.get("modelVersionInput") or vehicle.get("subtitle") or ""
    title = " ".join(
        p for p in (vehicle.get("make"), vehicle.get("model"), vehicle.get("modelVersionInput"))
        if p
    )
    return RawListing(
        source=SOURCE,
        source_id=_source_id(url),
        url=url,
        model=model,
        trim=trim,
        price_eur=_to_int((item.get("price") or {}).get("priceFormatted")),
        mileage_km=details.get("mileage_km"),
        year=details.get("year"),
        power_kw=details.get("power_kw"),
        battery_kwh=parse_battery_kwh(trim, title),
        condition=_condition(vehicle),
        location=" ".join(p for p in (loc.get("zip"), loc.get("city")) if p) or None,
        title=title,
    )
```

In `backend/carcatcher/scraping/vwde.py`, add the import:

```python
from carcatcher.scraping.battery import parse_battery_kwh
```

and replace `_car_to_listing` with:

```python
def _car_to_listing(car: dict, model: Model) -> RawListing | None:
    carid = car.get("carid")
    key = car.get("key")
    if not carid or not key:
        return None
    price = (car.get("parsedPrice") or {}).get("value")
    mileage = (car.get("mileage") or {}).get("raw_value")
    year_match = _YEAR_RE.match(car.get("initialreg") or "")
    dealer_city = ((car.get("dealer") or {}).get("city") or {}).get("value")
    trim = (car.get("subtitle") or {}).get("value") or car.get("title") or ""
    title = car.get("title") or ""
    return RawListing(
        source=SOURCE,
        source_id=str(carid),
        url=DETAIL_URL.format(key=key),
        model=model,
        trim=trim,
        price_eur=int(price) if price is not None else None,
        mileage_km=int(mileage) if mileage is not None else None,
        year=int(year_match.group(1)) if year_match else None,
        power_kw=_power_kw(car.get("powerLabel")),
        battery_kwh=parse_battery_kwh(trim, title),
        condition=_condition(car),
        location=dealer_city,
        title=title,
    )
```

In `backend/tests/test_crawl.py`, update the `_raw` helper to supply the new required field and accept a `location` override (needed later by Task 5's geocoding tests — adding it now avoids touching this signature twice):

```python
def _raw(source, source_id, model="id4", price=30000, location="Berlin"):
    return RawListing(
        source=source, source_id=source_id, url=f"https://x/{source_id}",
        model=model, trim="Pro", price_eur=price, mileage_km=1000, year=2024,
        power_kw=150, battery_kwh=None, condition="used", location=location, title="VW ID.4 Pro",
    )
```

In `backend/tests/test_api_refresh.py`, update `_raw`:

```python
def _raw(source_id):
    return RawListing(
        source="vw", source_id=source_id, url=f"https://x/{source_id}", model="id4",
        trim="Pro", price_eur=30000, mileage_km=1000, year=2024, power_kw=150,
        battery_kwh=None, condition="used", location="Berlin", title="VW ID.4 Pro",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest -v`
Expected: PASS, full suite green

- [ ] **Step 5: Commit**

```bash
git add backend/carcatcher/scraping/base.py backend/carcatcher/scraping/autoscout24.py \
  backend/carcatcher/scraping/vwde.py backend/tests/test_autoscout24.py \
  backend/tests/test_vwde.py backend/tests/test_crawl.py backend/tests/test_api_refresh.py
git commit -m "feat: parse battery_kwh into RawListing from both sources"
```

---

### Task 3: Add battery_kwh/latitude/longitude to the Listing DB model

**Files:**
- Modify: `backend/carcatcher/db/models.py`
- Modify: `backend/carcatcher/db/engine.py`
- Modify: `backend/tests/test_db_models.py`

**Interfaces:**
- Produces: `Listing.battery_kwh: float | None`, `Listing.latitude: float | None`, `Listing.longitude: float | None`. Consumed by Task 5 (`crawl.py`) and Task 7 (API layer).

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_db_models.py`, first fix the now-stale legacy-fields assertion — `battery_kwh` is being deliberately re-added, so remove it from the "must not exist" list:

```python
def test_removed_legacy_fields_are_not_on_the_model():
    for field in ("make", "deal_score", "ai_evaluation", "fair_price_estimate"):
        assert field not in Listing.model_fields
```

Then append these new tests:

```python
def test_battery_and_coordinates_default_to_none_and_round_trip():
    engine = _engine()
    with Session(engine) as session:
        session.add(
            Listing(source="vw", source_id="1", url="https://x/1", model="id4", title="A")
        )
        session.add(
            Listing(
                source="vw", source_id="2", url="https://x/2", model="id4", title="B",
                battery_kwh=82.0, latitude=52.52, longitude=13.40,
            )
        )
        session.commit()
        bare = session.exec(select(Listing).where(Listing.source_id == "1")).one()
        filled = session.exec(select(Listing).where(Listing.source_id == "2")).one()
        assert bare.battery_kwh is None
        assert bare.latitude is None
        assert bare.longitude is None
        assert filled.battery_kwh == 82.0
        assert filled.latitude == 52.52
        assert filled.longitude == 13.40


def test_init_db_adds_battery_and_coordinate_columns_to_an_existing_table_without_losing_data():
    """Mirrors the `tag` backfill test above for the three columns this
    feature adds — production may already have `tag` from a prior deploy but
    not yet these."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    with engine.connect() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE listing (
                id INTEGER PRIMARY KEY,
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                url TEXT NOT NULL,
                model TEXT NOT NULL,
                trim TEXT NOT NULL,
                price_eur INTEGER,
                mileage_km INTEGER,
                year INTEGER,
                power_kw INTEGER,
                condition TEXT NOT NULL,
                location TEXT,
                title TEXT NOT NULL,
                tag TEXT,
                status TEXT NOT NULL,
                first_seen_at DATETIME NOT NULL,
                last_seen_at DATETIME NOT NULL
            )
            """
        )
        conn.exec_driver_sql(
            "INSERT INTO listing (id, source, source_id, url, model, trim, condition, title, "
            "status, first_seen_at, last_seen_at) VALUES "
            "(1, 'vw', '1', 'https://x/1', 'id4', '', 'used', 'A', 'active', "
            "'2026-01-01T00:00:00', '2026-01-01T00:00:00')"
        )
        conn.commit()

    db_engine.set_engine(engine)
    try:
        db_engine.init_db()
        with Session(engine) as session:
            row = session.exec(select(Listing).where(Listing.source_id == "1")).one()
            assert row.battery_kwh is None
            assert row.latitude is None
            assert row.longitude is None
            assert row.title == "A"  # pre-existing data untouched
    finally:
        db_engine.set_engine(None)  # type: ignore[arg-type]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_db_models.py -v`
Expected: FAIL — `TypeError: 'battery_kwh' is an invalid keyword argument for Listing`

- [ ] **Step 3: Add the columns**

In `backend/carcatcher/db/models.py`, modify the `Listing` class (insert `battery_kwh` after `power_kw`, `latitude`/`longitude` after `location`):

```python
class Listing(SQLModel, table=True):
    __tablename__ = "listing"
    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_listing_source"),)

    id: int | None = Field(default=None, primary_key=True)

    source: str = Field(index=True)  # "autoscout24" | "vw"
    source_id: str
    url: str
    model: str = Field(index=True)  # "id3" | "id4"
    trim: str = ""
    price_eur: int | None = Field(default=None, index=True)
    mileage_km: int | None = None
    year: int | None = None
    power_kw: int | None = None
    battery_kwh: float | None = None
    condition: str = "used"  # "new" | "used"
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    title: str = ""
    tag: str | None = None  # "star" | "plus" | "minus" | "1".."10"

    status: str = Field(default=ListingStatus.ACTIVE.value, index=True)
    first_seen_at: datetime = Field(default_factory=utcnow)
    last_seen_at: datetime = Field(default_factory=utcnow, index=True)
```

In `backend/carcatcher/db/engine.py`, extend `_ADDED_COLUMNS`:

```python
_ADDED_COLUMNS: dict[str, str] = {
    "tag": "TEXT",
    "battery_kwh": "REAL",
    "latitude": "REAL",
    "longitude": "REAL",
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest -v`
Expected: PASS, full suite green

- [ ] **Step 5: Commit**

```bash
git add backend/carcatcher/db/models.py backend/carcatcher/db/engine.py backend/tests/test_db_models.py
git commit -m "feat: add battery_kwh/latitude/longitude columns to Listing"
```

---

### Task 4: Geocoding module (Nominatim client + Haversine distance)

**Files:**
- Create: `backend/carcatcher/geocoding.py`
- Test: `backend/tests/test_geocoding.py`

**Interfaces:**
- Produces: `Geocoder` (Protocol with `.geocode(location: str) -> tuple[float, float] | None`), `NominatimGeocoder` (concrete implementation, self-throttling to 1 req/sec), `haversine_km(lat1, lon1, lat2, lon2) -> float`. Consumed by Task 5 (crawl wiring), Task 6 (AppState), Task 7 (API distance computation).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_geocoding.py
"""Tests for Nominatim geocoding and Haversine distance."""

from __future__ import annotations

import httpx
import pytest
import respx

from carcatcher.geocoding import NOMINATIM_URL, NominatimGeocoder, haversine_km


@respx.mock
def test_geocode_returns_lat_lon_from_first_result():
    respx.get(NOMINATIM_URL).mock(
        return_value=httpx.Response(200, json=[{"lat": "49.4465237", "lon": "6.6269649"}])
    )
    geocoder = NominatimGeocoder()
    assert geocoder.geocode("66663 Merzig") == (49.4465237, 6.6269649)


@respx.mock
def test_geocode_returns_none_for_no_results():
    respx.get(NOMINATIM_URL).mock(return_value=httpx.Response(200, json=[]))
    geocoder = NominatimGeocoder()
    assert geocoder.geocode("Nonexistent Place XYZ") is None


@respx.mock
def test_geocode_returns_none_on_http_error():
    respx.get(NOMINATIM_URL).mock(return_value=httpx.Response(500))
    geocoder = NominatimGeocoder()
    assert geocoder.geocode("Berlin") is None


@respx.mock
def test_geocode_returns_none_on_malformed_json():
    respx.get(NOMINATIM_URL).mock(return_value=httpx.Response(200, text="not json"))
    geocoder = NominatimGeocoder()
    assert geocoder.geocode("Berlin") is None


@respx.mock
def test_geocode_sends_a_descriptive_user_agent_and_germany_hint():
    route = respx.get(NOMINATIM_URL).mock(
        return_value=httpx.Response(200, json=[{"lat": "1", "lon": "2"}])
    )
    NominatimGeocoder().geocode("24941 Flensburg")
    request = route.calls.last.request
    assert "carcatcher" in request.headers["User-Agent"]
    assert request.url.params["q"] == "24941 Flensburg, Germany"


@respx.mock
def test_throttles_to_one_request_per_second(monkeypatch):
    respx.get(NOMINATIM_URL).mock(
        return_value=httpx.Response(200, json=[{"lat": "1", "lon": "2"}])
    )
    sleep_calls: list[float] = []
    times = iter([100.0, 100.2, 100.2])
    monkeypatch.setattr("carcatcher.geocoding.time.monotonic", lambda: next(times))
    monkeypatch.setattr("carcatcher.geocoding.time.sleep", lambda s: sleep_calls.append(s))

    geocoder = NominatimGeocoder()
    geocoder.geocode("A")
    geocoder.geocode("B")
    assert sleep_calls == [pytest.approx(0.8)]


def test_haversine_km_same_point_is_zero():
    assert haversine_km(49.44, 6.63, 49.44, 6.63) == 0.0


def test_haversine_km_berlin_to_munich():
    berlin = (52.5200, 13.4050)
    munich = (48.1351, 11.5820)
    assert haversine_km(*berlin, *munich) == pytest.approx(504.4, abs=1.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_geocoding.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'carcatcher.geocoding'`

- [ ] **Step 3: Write the implementation**

```python
# backend/carcatcher/geocoding.py
"""Geocoding via the free Nominatim (OpenStreetMap) API, plus great-circle
distance. Geocoding failures never raise — a listing simply keeps null
coordinates rather than failing the crawl that's fetching it."""

from __future__ import annotations

import logging
import time
from math import asin, cos, radians, sin, sqrt
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "carcatcher/0.1 (personal used-car tracker; github.com/kaijurtin/carcatcher)"
MIN_REQUEST_INTERVAL_SECONDS = 1.0  # Nominatim usage policy cap: 1 request/second
_EARTH_RADIUS_KM = 6371.0


class Geocoder(Protocol):
    def geocode(self, location: str) -> tuple[float, float] | None: ...


class NominatimGeocoder:
    """Looks up (latitude, longitude) for a free-text German location string
    (e.g. "24941 Flensburg" or "Kölln-Reisiek") via Nominatim. Self-throttles
    to Nominatim's 1 request/second usage-policy cap."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=10.0, headers={"User-Agent": USER_AGENT})
        self._last_request_at: float | None = None

    def geocode(self, location: str) -> tuple[float, float] | None:
        self._throttle()
        try:
            resp = self._client.get(
                NOMINATIM_URL, params={"q": f"{location}, Germany", "format": "json", "limit": 1}
            )
            resp.raise_for_status()
            results = resp.json()
        except (httpx.HTTPError, ValueError):
            logger.warning("geocoding failed for location=%r", location, exc_info=True)
            return None
        finally:
            self._last_request_at = time.monotonic()
        if not results:
            return None
        try:
            return float(results[0]["lat"]), float(results[0]["lon"])
        except (KeyError, TypeError, ValueError):
            return None

    def _throttle(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
            time.sleep(MIN_REQUEST_INTERVAL_SECONDS - elapsed)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in kilometers."""
    rlat1, rlon1, rlat2, rlon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = rlat2 - rlat1, rlon2 - rlon1
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * asin(sqrt(a))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_geocoding.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/carcatcher/geocoding.py backend/tests/test_geocoding.py
git commit -m "feat: add Nominatim geocoding client and Haversine distance"
```

---

### Task 5: Wire geocoding into crawl orchestration

**Files:**
- Modify: `backend/carcatcher/crawl.py`
- Modify: `backend/tests/test_crawl.py`

**Interfaces:**
- Consumes: `Geocoder` protocol from Task 4; `Listing.battery_kwh/latitude/longitude` from Task 3; `RawListing.battery_kwh` from Task 2.
- Produces: `run_crawl(session, parsers, geocoder: Geocoder | None = None) -> CrawlSummary` — `geocoder=None` (the default) skips geocoding entirely, so nothing calls Nominatim unless a geocoder is explicitly passed. Consumed by Task 6 (`refresh.py`).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_crawl.py`:

```python
class FakeGeocoder:
    def __init__(self, coords_by_location):
        self._coords = coords_by_location
        self.calls: list[str] = []

    def geocode(self, location):
        self.calls.append(location)
        return self._coords.get(location)


def test_geocodes_a_new_listing_with_a_location():
    engine = _engine()
    geocoder = FakeGeocoder({"Berlin": (52.52, 13.40)})
    with Session(engine) as session:
        run_crawl(
            session,
            {"vw": FakeParser("vw", {"id4": [_raw("vw", "1")], "id3": []})},
            geocoder,
        )
        row = session.exec(select(Listing).where(Listing.source_id == "1")).one()
        assert row.latitude == 52.52
        assert row.longitude == 13.40


def test_no_geocoder_leaves_coordinates_null():
    engine = _engine()
    with Session(engine) as session:
        run_crawl(session, {"vw": FakeParser("vw", {"id4": [_raw("vw", "1")], "id3": []})})
        row = session.exec(select(Listing).where(Listing.source_id == "1")).one()
        assert row.latitude is None
        assert row.longitude is None


def test_geocoding_failure_leaves_coordinates_null():
    engine = _engine()
    geocoder = FakeGeocoder({})  # no known locations -> geocode() returns None for everything
    with Session(engine) as session:
        run_crawl(
            session,
            {"vw": FakeParser("vw", {"id4": [_raw("vw", "1", location="Nowhereville")], "id3": []})},
            geocoder,
        )
        row = session.exec(select(Listing).where(Listing.source_id == "1")).one()
        assert row.latitude is None
        assert geocoder.calls == ["Nowhereville"]


def test_reuses_cached_coordinates_for_a_repeated_location_within_one_crawl():
    engine = _engine()
    geocoder = FakeGeocoder({"Berlin": (52.52, 13.40)})
    with Session(engine) as session:
        run_crawl(
            session,
            {
                "vw": FakeParser(
                    "vw",
                    {
                        "id4": [_raw("vw", "1", location="Berlin"), _raw("vw", "2", location="Berlin")],
                        "id3": [],
                    },
                )
            },
            geocoder,
        )
        assert geocoder.calls == ["Berlin"]  # geocoded once, reused for the second listing
        rows = {r.source_id: r for r in session.exec(select(Listing)).all()}
        assert rows["1"].latitude == 52.52
        assert rows["2"].latitude == 52.52


def test_reuses_coordinates_already_known_in_the_db_without_calling_the_geocoder():
    engine = _engine()
    with Session(engine) as session:
        run_crawl(
            session,
            {"vw": FakeParser("vw", {"id4": [_raw("vw", "1", location="Berlin")], "id3": []})},
            FakeGeocoder({"Berlin": (52.52, 13.40)}),
        )

    # Second crawl, a different listing, same location string, with a geocoder
    # that has no known coordinates — proves the DB-known coordinate is reused
    # instead of calling the (here, failing) live geocoder.
    geocoder = FakeGeocoder({})
    with Session(engine) as session:
        run_crawl(
            session,
            {"vw": FakeParser("vw", {"id4": [_raw("vw", "2", location="Berlin")], "id3": []})},
            geocoder,
        )
        row = session.exec(select(Listing).where(Listing.source_id == "2")).one()
        assert row.latitude == 52.52
        assert geocoder.calls == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_crawl.py -v`
Expected: FAIL — `TypeError: run_crawl() takes 2 positional arguments but 3 were given`

- [ ] **Step 3: Wire geocoding into `run_crawl`**

Replace the full contents of `backend/carcatcher/crawl.py`:

```python
"""Crawl orchestration: fetch every source x model, upsert into `Listing`, mark
listings that disappeared from a successfully-crawled source as `gone`."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlmodel import Session, select

from carcatcher.db.models import Listing, ListingStatus
from carcatcher.geocoding import Geocoder
from carcatcher.scraping.base import Model, Parser, RawListing

logger = logging.getLogger(__name__)

MODELS: tuple[Model, ...] = ("id3", "id4")


@dataclass
class CrawlSummary:
    added: int = 0
    updated: int = 0
    gone: int = 0
    failed_sources: list[str] = field(default_factory=list)
    refreshed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def run_crawl(
    session: Session, parsers: dict[str, Parser], geocoder: Geocoder | None = None
) -> CrawlSummary:
    summary = CrawlSummary()
    seen_keys: set[tuple[str, str]] = set()
    succeeded_sources: set[str] = set()
    location_cache: dict[str, tuple[float, float] | None] = {}

    for name, parser in parsers.items():
        source_ok = True
        for model in MODELS:
            try:
                raw_listings = parser.fetch_listings(model)
            except Exception:
                logger.exception("crawl failed for source=%s model=%s", name, model)
                if name not in summary.failed_sources:
                    summary.failed_sources.append(name)
                source_ok = False
                continue
            for raw in raw_listings:
                seen_keys.add((raw.source, raw.source_id))
                listing, inserted = _upsert(session, raw)
                if inserted:
                    summary.added += 1
                else:
                    summary.updated += 1
                if geocoder is not None:
                    _resolve_coordinates(session, geocoder, location_cache, raw, listing)
        if source_ok:
            succeeded_sources.add(name)

    summary.gone = _mark_gone(session, succeeded_sources, seen_keys)
    session.commit()
    return summary


def _upsert(session: Session, raw: RawListing) -> tuple[Listing, bool]:
    """Insert or update the `Listing` row for `raw`. Returns (listing, True if
    newly inserted)."""
    now = datetime.now(timezone.utc)
    existing = session.exec(
        select(Listing).where(Listing.source == raw.source, Listing.source_id == raw.source_id)
    ).first()
    if existing:
        existing.url = raw.url
        existing.model = raw.model
        existing.trim = raw.trim
        existing.price_eur = raw.price_eur
        existing.mileage_km = raw.mileage_km
        existing.year = raw.year
        existing.power_kw = raw.power_kw
        existing.battery_kwh = raw.battery_kwh
        existing.condition = raw.condition
        existing.location = raw.location
        existing.title = raw.title
        existing.status = ListingStatus.ACTIVE.value
        existing.last_seen_at = now
        session.add(existing)
        return existing, False
    listing = Listing(
        source=raw.source, source_id=raw.source_id, url=raw.url, model=raw.model,
        trim=raw.trim, price_eur=raw.price_eur, mileage_km=raw.mileage_km,
        year=raw.year, power_kw=raw.power_kw, battery_kwh=raw.battery_kwh,
        condition=raw.condition, location=raw.location, title=raw.title,
        status=ListingStatus.ACTIVE.value, first_seen_at=now, last_seen_at=now,
    )
    session.add(listing)
    return listing, True


def _resolve_coordinates(
    session: Session,
    geocoder: Geocoder,
    cache: dict[str, tuple[float, float] | None],
    raw: RawListing,
    listing: Listing,
) -> None:
    """Fill `listing.latitude`/`longitude` from `raw.location`, reusing
    coordinates already known for that exact location string — first from
    this crawl's in-memory cache, then from any other listing already
    geocoded in the DB — before ever calling the live geocoder."""
    if listing.latitude is not None and listing.longitude is not None:
        return
    if not raw.location:
        return
    if raw.location not in cache:
        cache[raw.location] = _lookup_known_coordinates(session, raw.location) or geocoder.geocode(
            raw.location
        )
    coords = cache[raw.location]
    if coords is not None:
        listing.latitude, listing.longitude = coords
        session.add(listing)


def _lookup_known_coordinates(session: Session, location: str) -> tuple[float, float] | None:
    row = session.exec(
        select(Listing.latitude, Listing.longitude)
        .where(Listing.location == location, Listing.latitude.is_not(None))
        .limit(1)
    ).first()
    return (row[0], row[1]) if row else None


def _mark_gone(
    session: Session, succeeded_sources: set[str], seen_keys: set[tuple[str, str]]
) -> int:
    """Mark `gone` any active listing whose source completed this crawl but whose
    (source, source_id) wasn't seen. Listings from a failed source are left alone —
    we have no evidence they actually disappeared."""
    if not succeeded_sources:
        return 0
    active = session.exec(
        select(Listing).where(
            Listing.status == ListingStatus.ACTIVE.value,
            Listing.source.in_(succeeded_sources),  # type: ignore[union-attr]
        )
    ).all()
    count = 0
    for listing in active:
        if (listing.source, listing.source_id) not in seen_keys:
            listing.status = ListingStatus.GONE.value
            session.add(listing)
            count += 1
    return count
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest -v`
Expected: PASS, full suite green

- [ ] **Step 5: Commit**

```bash
git add backend/carcatcher/crawl.py backend/tests/test_crawl.py
git commit -m "feat: geocode listing coordinates during crawl"
```

---

### Task 6: Wire a real geocoder into AppState and the refresh route

**Files:**
- Modify: `backend/carcatcher/app_state.py`
- Modify: `backend/carcatcher/api/routes/refresh.py`
- Test: `backend/tests/test_app_state.py`

**Interfaces:**
- Consumes: `NominatimGeocoder` from Task 4; `run_crawl(session, parsers, geocoder)` from Task 5.
- Produces: `AppState.geocoder: Geocoder | None = None`. Consumed by Task 7 only indirectly (no dependency); this task's own scope is limited to production wiring.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_app_state.py
"""Tests for process-wide AppState construction."""

from __future__ import annotations

from carcatcher.app_state import build_state
from carcatcher.geocoding import NominatimGeocoder


def test_build_state_wires_a_real_geocoder():
    state = build_state()
    assert isinstance(state.geocoder, NominatimGeocoder)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_app_state.py -v`
Expected: FAIL — `AttributeError: 'AppState' object has no attribute 'geocoder'`

- [ ] **Step 3: Wire the geocoder**

Replace the full contents of `backend/carcatcher/app_state.py`:

```python
"""Process-wide singleton: the parser registry and geocoder. Built in the
FastAPI lifespan; overridable in tests via `set_state`."""

from __future__ import annotations

from dataclasses import dataclass

from carcatcher.geocoding import Geocoder, NominatimGeocoder
from carcatcher.scraping.base import Parser
from carcatcher.scraping.registry import build_registry


@dataclass
class AppState:
    parsers: dict[str, Parser]
    geocoder: Geocoder | None = None


_state: AppState | None = None


def build_state() -> AppState:
    return AppState(parsers=build_registry(), geocoder=NominatimGeocoder())


def set_state(state: AppState | None) -> None:
    global _state
    _state = state


def get_state() -> AppState:
    if _state is None:
        raise RuntimeError("AppState not initialized")
    return _state
```

In `backend/carcatcher/api/routes/refresh.py`, replace the `refresh` function body:

```python
@router.post("/refresh", response_model=RefreshSummary)
def refresh() -> RefreshSummary:
    state = get_state()
    with Session(get_engine()) as session:
        summary = run_crawl(session, state.parsers, state.geocoder)
    return RefreshSummary(
        added=summary.added,
        updated=summary.updated,
        gone=summary.gone,
        failed_sources=summary.failed_sources,
        refreshed_at=summary.refreshed_at,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest -v`
Expected: PASS, full suite green (existing `test_api_refresh.py` tests still pass unmodified — they construct `AppState(parsers=...)` without a geocoder, which now defaults to `None`, so `run_crawl` skips geocoding exactly as before this task)

- [ ] **Step 5: Commit**

```bash
git add backend/carcatcher/app_state.py backend/carcatcher/api/routes/refresh.py backend/tests/test_app_state.py
git commit -m "feat: wire a real Nominatim geocoder into production AppState"
```

---

### Task 7: Expose battery_kwh and distance_km through the API

**Files:**
- Modify: `backend/carcatcher/config.py`
- Modify: `backend/carcatcher/api/routes/listings.py`
- Modify: `backend/tests/test_api_listings.py`

**Interfaces:**
- Consumes: `haversine_km` from Task 4; `Listing.battery_kwh/latitude/longitude` from Task 3.
- Produces: `ListingRead.battery_kwh: float | None`, `ListingRead.distance_km: float | None`. Consumed by the frontend (Task 9).

- [ ] **Step 1: Write the failing tests**

Add `import pytest` to the top of `backend/tests/test_api_listings.py` (it doesn't import it yet), then append:

```python
def test_battery_kwh_included_in_response(client, test_engine):
    _seed(test_engine, source_id="1", battery_kwh=82.0)
    resp = client.get("/api/listings")
    assert resp.json()[0]["battery_kwh"] == 82.0


def test_battery_kwh_defaults_to_null(client, test_engine):
    _seed(test_engine, source_id="1")
    resp = client.get("/api/listings")
    assert resp.json()[0]["battery_kwh"] is None


def test_distance_km_is_null_without_coordinates(client, test_engine):
    _seed(test_engine, source_id="1")
    resp = client.get("/api/listings")
    assert resp.json()[0]["distance_km"] is None


def test_distance_km_is_zero_at_the_home_point(client, test_engine):
    from carcatcher.config import get_settings

    settings = get_settings()
    _seed(
        test_engine, source_id="1",
        latitude=settings.home_latitude, longitude=settings.home_longitude,
    )
    resp = client.get("/api/listings")
    assert resp.json()[0]["distance_km"] == 0.0


def test_distance_km_computed_from_coordinates(client, test_engine):
    # Berlin, ~504 km from the fixed home point (66663 Merzig) — sanity-checks
    # that a real, non-zero coordinate pair produces a plausible distance.
    _seed(test_engine, source_id="1", latitude=52.5200, longitude=13.4050)
    resp = client.get("/api/listings")
    assert resp.json()[0]["distance_km"] == pytest.approx(504.4, abs=1.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_api_listings.py -v`
Expected: FAIL — `KeyError: 'battery_kwh'` (field not yet in the response)

- [ ] **Step 3: Add the home-point constants and wire the API layer**

In `backend/carcatcher/config.py`, add to `Settings`:

```python
    # Fixed home point for distance-to-listing sorting: Nominatim's centroid
    # for German postal code 66663 (Merzig), verified live 2026-08-12.
    home_latitude: float = 49.4465237
    home_longitude: float = 6.6269649
```

Replace the full contents of `backend/carcatcher/api/routes/listings.py`:

```python
"""Listing query endpoint: filtered list of active (or all) listings."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import asc
from sqlmodel import Session, func, select

from carcatcher.config import get_settings
from carcatcher.db.engine import get_session
from carcatcher.db.models import Listing, ListingStatus
from carcatcher.geocoding import haversine_km

router = APIRouter()

TagValue = Literal[
    "star", "plus", "minus", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"
]


class ListingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    source_id: str
    url: str
    model: str
    trim: str
    price_eur: int | None
    mileage_km: int | None
    year: int | None
    power_kw: int | None
    battery_kwh: float | None
    condition: str
    location: str | None
    title: str
    tag: str | None
    status: str
    first_seen_at: datetime
    last_seen_at: datetime
    distance_km: float | None = None


class TagUpdate(BaseModel):
    tag: TagValue | None


def _to_read(listing: Listing) -> ListingRead:
    """Build the API representation of `listing`, computing `distance_km` from
    its coordinates against the fixed home point — never stored, always
    derived, so it can't go stale if the home point ever changes."""
    read = ListingRead.model_validate(listing)
    if listing.latitude is not None and listing.longitude is not None:
        settings = get_settings()
        read.distance_km = round(
            haversine_km(
                listing.latitude, listing.longitude, settings.home_latitude, settings.home_longitude
            ),
            1,
        )
    return read


@router.get("/listings", response_model=list[ListingRead])
def list_listings(
    session: Session = Depends(get_session),
    model: Literal["id3", "id4"] | None = None,
    source: str | None = None,
    max_price: int | None = None,
    max_km: int | None = None,
    trim: str | None = None,
    status: str = ListingStatus.ACTIVE.value,
) -> list[ListingRead]:
    conditions = []
    if status != "all":
        conditions.append(Listing.status == status)
    if model:
        conditions.append(Listing.model == model)
    if source:
        conditions.append(Listing.source == source)
    if max_price is not None:
        conditions.append(Listing.price_eur <= max_price)
    if max_km is not None:
        conditions.append(Listing.mileage_km <= max_km)
    if trim:
        conditions.append(func.lower(Listing.trim).like(f"%{trim.lower()}%"))
    stmt = (
        select(Listing)
        .where(*conditions)
        .order_by(Listing.price_eur.is_(None), asc(Listing.price_eur), Listing.id)
    )
    items = session.exec(stmt).all()
    return [_to_read(i) for i in items]


@router.patch("/listings/{listing_id}/tag", response_model=ListingRead)
def set_listing_tag(
    listing_id: int, payload: TagUpdate, session: Session = Depends(get_session)
) -> ListingRead:
    listing = session.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")
    listing.tag = payload.tag
    session.add(listing)
    session.commit()
    session.refresh(listing)
    return _to_read(listing)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest -v`
Expected: PASS, full suite green

- [ ] **Step 5: Commit**

```bash
git add backend/carcatcher/config.py backend/carcatcher/api/routes/listings.py backend/tests/test_api_listings.py
git commit -m "feat: expose battery_kwh and computed distance_km via the API"
```

---

### Task 8: Multi-column sort mechanism in ListingsTable

**Files:**
- Modify: `frontend/src/components/ListingsTable.tsx`
- Modify: `frontend/src/components/ListingsTable.test.tsx`

**Interfaces:**
- Produces: `SortKey[]` sort state, `onSort(field, shiftKey)` handler, rank-badge UI. No change to `Listing`/`SortField` yet — this task only generalizes the sort *mechanism* using existing fields, so it doesn't depend on Task 7's new API fields.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/components/ListingsTable.test.tsx` (inside the existing `describe("ListingsTable", ...)` block, after the existing sort tests):

```tsx
  it("adds a shift+click column as a tiebreaker without resetting the primary sort", () => {
    const tieBreakListings: Listing[] = [
      { ...listing, id: 1, trim: "Bravo", price_eur: 20000 },
      { ...listing, id: 2, trim: "Alpha", price_eur: 20000 },
      { ...listing, id: 3, trim: "Charlie", price_eur: 10000 },
    ];
    render(<ListingsTable items={tieBreakListings} filters={{}} onFilterChange={noop} onTagChange={noop} />);

    fireEvent.click(screen.getByRole("button", { name: "Sort by Price" }));
    fireEvent.click(screen.getByRole("button", { name: "Sort by Trim" }), { shiftKey: true });

    const order = rowTrims();
    expect(order[0]).toContain("Charlie"); // 10000, sole cheapest
    expect(order[1]).toContain("Alpha"); // tied at 20000, "Alpha" < "Bravo"
    expect(order[2]).toContain("Bravo");
  });

  it("shift+click on an already-active column toggles its direction in place", () => {
    const tieBreakListings: Listing[] = [
      { ...listing, id: 1, trim: "Bravo", price_eur: 20000 },
      { ...listing, id: 2, trim: "Alpha", price_eur: 20000 },
      { ...listing, id: 3, trim: "Charlie", price_eur: 10000 },
    ];
    render(<ListingsTable items={tieBreakListings} filters={{}} onFilterChange={noop} onTagChange={noop} />);

    fireEvent.click(screen.getByRole("button", { name: "Sort by Price" }));
    fireEvent.click(screen.getByRole("button", { name: "Sort by Trim" }), { shiftKey: true });
    fireEvent.click(screen.getByRole("button", { name: "Sort by Trim" }), { shiftKey: true });

    const order = rowTrims();
    expect(order[0]).toContain("Charlie");
    expect(order[1]).toContain("Bravo"); // tiebreaker now descending: "Bravo" > "Alpha"
    expect(order[2]).toContain("Alpha");
  });

  it("plain click resets a multi-column sort back to a single key", () => {
    const tieBreakListings: Listing[] = [
      { ...listing, id: 1, trim: "Bravo", price_eur: 20000 },
      { ...listing, id: 2, trim: "Alpha", price_eur: 10000 },
    ];
    render(<ListingsTable items={tieBreakListings} filters={{}} onFilterChange={noop} onTagChange={noop} />);

    fireEvent.click(screen.getByRole("button", { name: "Sort by Price" }));
    fireEvent.click(screen.getByRole("button", { name: "Sort by Trim" }), { shiftKey: true });
    fireEvent.click(screen.getByRole("button", { name: "Sort by Trim" })); // plain click

    const order = rowTrims();
    expect(order[0]).toContain("Alpha"); // ascending by Trim alone now
    expect(order[1]).toContain("Bravo");
  });

  it("shows a rank badge on each header only when more than one sort key is active", () => {
    render(<ListingsTable items={threeListings} filters={{}} onFilterChange={noop} onTagChange={noop} />);

    fireEvent.click(screen.getByRole("button", { name: "Sort by Price" }));
    expect(screen.getByRole("button", { name: "Sort by Price" }).textContent).not.toMatch(/①/);

    fireEvent.click(screen.getByRole("button", { name: "Sort by Trim" }), { shiftKey: true });
    expect(screen.getByRole("button", { name: "Sort by Price" }).textContent).toContain("①");
    expect(screen.getByRole("button", { name: "Sort by Trim" }).textContent).toContain("②");
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm run test`
Expected: FAIL — the new shift+click tests fail (plain click still works because the single-key click behavior is unchanged so far)

- [ ] **Step 3: Generalize the sort state to a chain**

Replace the full contents of `frontend/src/components/ListingsTable.tsx`:

```tsx
import { useState } from "react";
import type { Listing } from "../types";
import { formatKm, formatPrice, formatYear } from "../lib/format";

export const SOURCE_LABEL: Record<string, string> = {
  vw: "VW.de",
  autoscout24: "AutoScout24",
};

const SOURCE_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "All sources" },
  { value: "vw", label: "VW.de" },
  { value: "autoscout24", label: "AutoScout24" },
];

const MODEL_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "ID.3 + ID.4" },
  { value: "id3", label: "ID.3" },
  { value: "id4", label: "ID.4" },
];

const MODEL_LABEL: Record<string, string> = { id3: "ID.3", id4: "ID.4" };

const TAG_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "—" },
  { value: "star", label: "★" },
  { value: "plus", label: "+" },
  { value: "minus", label: "−" },
  ...Array.from({ length: 10 }, (_, i) => ({ value: String(i + 1), label: String(i + 1) })),
];

export interface TableFilters {
  model?: string;
  source?: string;
  max_price?: number;
  max_km?: number;
  trim?: string;
}

const num = (v: string): number | undefined => (v.trim() === "" ? undefined : Number(v));

type SortField =
  | "model"
  | "trim"
  | "price_eur"
  | "mileage_km"
  | "year"
  | "power_kw"
  | "condition"
  | "location"
  | "source";

interface SortKey {
  field: SortField;
  direction: "asc" | "desc";
}

const TEXT_SORT_FIELDS = new Set<SortField>(["model", "trim", "condition", "location", "source"]);

const CONDITION_LABEL: Record<string, string> = { new: "Neu", used: "Gebraucht" };

// Condition sorts by its displayed label, not the raw "new"/"used" value, so
// ascending/descending order matches what the user actually sees in the cell.
function sortValue(item: Listing, field: SortField): unknown {
  if (field === "condition") {
    return CONDITION_LABEL[item.condition] ?? item.condition;
  }
  return item[field];
}

function compareValues(av: unknown, bv: unknown, isText: boolean, direction: "asc" | "desc"): number {
  if (av == null && bv == null) return 0;
  if (av == null) return 1; // nulls always sort last, regardless of direction
  if (bv == null) return -1;
  const cmp = isText
    ? String(av).localeCompare(String(bv), "de")
    : (av as number) - (bv as number);
  return direction === "asc" ? cmp : -cmp;
}

function sortListings(items: Listing[], sort: SortKey[]): Listing[] {
  if (sort.length === 0) return items;
  return [...items].sort((a, b) => {
    for (const key of sort) {
      const isText = TEXT_SORT_FIELDS.has(key.field);
      const cmp = compareValues(sortValue(a, key.field), sortValue(b, key.field), isText, key.direction);
      if (cmp !== 0) return cmp;
    }
    return 0;
  });
}

const RANK_BADGES = ["①", "②", "③", "④", "⑤"];

function rankBadge(index: number): string {
  return RANK_BADGES[index] ?? `(${index + 1})`;
}

interface ListingsTableProps {
  items: Listing[];
  filters: TableFilters;
  onFilterChange: (next: TableFilters) => void;
  onTagChange: (id: number, tag: string | null) => void;
}

export function ListingsTable({ items, filters, onFilterChange, onTagChange }: ListingsTableProps) {
  const f = filters;
  const set = (patch: Partial<TableFilters>) => onFilterChange({ ...f, ...patch });

  const [sort, setSort] = useState<SortKey[]>([]);
  const onSort = (field: SortField, shiftKey: boolean) => {
    setSort((prev) => {
      if (!shiftKey) {
        const isSoleActiveKey = prev.length === 1 && prev[0].field === field;
        const direction = isSoleActiveKey && prev[0].direction === "asc" ? "desc" : "asc";
        return [{ field, direction }];
      }
      const idx = prev.findIndex((k) => k.field === field);
      if (idx === -1) return [...prev, { field, direction: "asc" }];
      return prev.map((k, i) => (i === idx ? { ...k, direction: k.direction === "asc" ? "desc" : "asc" } : k));
    });
  };
  const sortedItems = sortListings(items, sort);

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <SortableHeader label="Model" field="model" sort={sort} onSort={onSort} />
            <SortableHeader label="Trim" field="trim" sort={sort} onSort={onSort} />
            <SortableHeader label="Price" field="price_eur" sort={sort} onSort={onSort} />
            <SortableHeader label="KM" field="mileage_km" sort={sort} onSort={onSort} />
            <SortableHeader label="Year" field="year" sort={sort} onSort={onSort} />
            <SortableHeader label="Power" field="power_kw" sort={sort} onSort={onSort} />
            <SortableHeader label="Condition" field="condition" sort={sort} onSort={onSort} />
            <SortableHeader label="Location" field="location" sort={sort} onSort={onSort} />
            <SortableHeader label="Source" field="source" sort={sort} onSort={onSort} />
            <th className="px-4 py-3 font-medium">Tag</th>
            <th className="px-4 py-3 font-medium" />
          </tr>
          <tr className="border-t border-slate-200 bg-white text-slate-600 normal-case tracking-normal">
            <th className="px-4 py-2">
              <select
                aria-label="Filter model"
                value={f.model ?? ""}
                onChange={(e) => set({ model: e.target.value || undefined })}
                className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-normal text-slate-700"
              >
                {MODEL_OPTIONS.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
            </th>
            <th className="px-4 py-2">
              <input
                type="text"
                aria-label="Filter trim"
                placeholder="contains, e.g. Pro"
                value={f.trim ?? ""}
                onChange={(e) => set({ trim: e.target.value || undefined })}
                className="w-32 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-normal text-slate-700"
              />
            </th>
            <th className="px-4 py-2">
              <input
                type="number"
                inputMode="numeric"
                aria-label="Max price"
                placeholder="max €"
                value={f.max_price ?? ""}
                onChange={(e) => set({ max_price: num(e.target.value) })}
                className="w-24 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-normal text-slate-700"
              />
            </th>
            <th className="px-4 py-2">
              <input
                type="number"
                inputMode="numeric"
                aria-label="Max km"
                placeholder="max km"
                value={f.max_km ?? ""}
                onChange={(e) => set({ max_km: num(e.target.value) })}
                className="w-24 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-normal text-slate-700"
              />
            </th>
            <th className="px-4 py-2" />
            <th className="px-4 py-2" />
            <th className="px-4 py-2" />
            <th className="px-4 py-2" />
            <th className="px-4 py-2">
              <select
                aria-label="Filter source"
                value={f.source ?? ""}
                onChange={(e) => set({ source: e.target.value || undefined })}
                className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-normal text-slate-700"
              >
                {SOURCE_OPTIONS.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </th>
            <th className="px-4 py-2" />
            <th className="px-4 py-2" />
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.length === 0 ? (
            <tr>
              <td colSpan={11} className="px-4 py-12 text-center text-slate-500">
                No listings match these filters.
              </td>
            </tr>
          ) : (
            sortedItems.map((l) => (
              <tr key={l.id} className="hover:bg-slate-50">
                <td className="whitespace-nowrap px-4 py-3 font-medium text-slate-900">
                  {MODEL_LABEL[l.model] ?? l.model}
                </td>
                <td className="max-w-md px-4 py-3">
                  <span className="line-clamp-1 text-slate-700">{l.trim || l.title}</span>
                </td>
                <td className="whitespace-nowrap px-4 py-3 font-semibold text-slate-900">
                  {formatPrice(l.price_eur)}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-600">{formatKm(l.mileage_km)}</td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-600">{formatYear(l.year)}</td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                  {l.power_kw != null ? `${l.power_kw} kW` : "—"}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                  {CONDITION_LABEL[l.condition] ?? l.condition}
                </td>
                <td className="max-w-[12rem] px-4 py-3 text-slate-600">
                  <span className="line-clamp-1">{l.location ?? "—"}</span>
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-500">
                  {SOURCE_LABEL[l.source] ?? l.source}
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <select
                    aria-label={`Tag for ${l.trim || l.title}`}
                    value={l.tag ?? ""}
                    onChange={(e) => onTagChange(l.id, e.target.value || null)}
                    className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-700"
                  >
                    {TAG_OPTIONS.map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <a
                    href={l.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm font-medium text-sky-600 hover:text-sky-700"
                  >
                    View ↗
                  </a>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

interface SortableHeaderProps {
  label: string;
  field: SortField;
  sort: SortKey[];
  onSort: (field: SortField, shiftKey: boolean) => void;
}

function SortableHeader({ label, field, sort, onSort }: SortableHeaderProps) {
  const index = sort.findIndex((k) => k.field === field);
  const active = index !== -1;
  const arrow = active ? (sort[index].direction === "asc" ? " ▲" : " ▼") : "";
  const badge = active && sort.length > 1 ? ` ${rankBadge(index)}` : "";
  return (
    <th className="px-4 py-3 font-medium">
      <button
        type="button"
        onClick={(e) => onSort(field, e.shiftKey)}
        aria-label={`Sort by ${label}`}
        className={`uppercase tracking-wide ${active ? "text-slate-800" : "text-slate-500 hover:text-slate-700"}`}
      >
        {label}
        {badge}
        {arrow}
      </button>
    </th>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm run test`
Expected: PASS, full suite green (existing single-column sort tests still pass unchanged — `fireEvent.click` without `shiftKey` behaves exactly as before)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ListingsTable.tsx frontend/src/components/ListingsTable.test.tsx
git commit -m "feat: support multi-column sort via shift+click"
```

---

### Task 9: Battery and Distance columns end-to-end on the frontend

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/format.ts`
- Modify: `frontend/src/components/ListingsTable.tsx`
- Modify: `frontend/src/components/ListingsTable.test.tsx`
- Modify: `frontend/src/pages/Dashboard.test.tsx`

**Interfaces:**
- Consumes: `battery_kwh`/`distance_km` from Task 7's API response; `SortKey[]`/`onSort` mechanism from Task 8.
- Produces: `Listing.battery_kwh: number | null`, `Listing.distance_km: number | null`; `formatBatteryKwh`, `formatDistanceKm`.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/components/ListingsTable.test.tsx`, add `battery_kwh: null, distance_km: null,` to the base `listing` fixture (after `power_kw: 125,`):

```tsx
const listing: Listing = {
  id: 1,
  source: "vw",
  source_id: "1",
  url: "https://example.com/1",
  model: "id4",
  trim: "Pro Performance",
  price_eur: 34410,
  mileage_km: 10937,
  year: 2025,
  power_kw: 125,
  battery_kwh: null,
  condition: "used",
  location: "Berlin",
  distance_km: null,
  title: "VW ID.4 Pro",
  tag: null,
  status: "active",
  first_seen_at: "2026-08-11T00:00:00Z",
  last_seen_at: "2026-08-11T00:00:00Z",
};
```

Then append these tests to the `describe` block:

```tsx
  it("renders battery capacity and distance when present", () => {
    render(
      <ListingsTable
        items={[{ ...listing, battery_kwh: 82, distance_km: 12.3 }]}
        filters={{}}
        onFilterChange={noop}
        onTagChange={noop}
      />,
    );
    expect(screen.getByText("82 kWh")).toBeInTheDocument();
    expect(screen.getByText("12 km")).toBeInTheDocument();
  });

  it("shows — for battery capacity and distance when null", () => {
    render(<ListingsTable items={[listing]} filters={{}} onFilterChange={noop} onTagChange={noop} />);
    const cells = screen.getAllByRole("cell").map((c) => c.textContent);
    expect(cells.filter((c) => c === "—")).toHaveLength(2);
  });

  it("sorts by Battery with nulls last", () => {
    const batteryListings: Listing[] = [
      { ...listing, id: 1, trim: "Charlie", battery_kwh: 82 },
      { ...listing, id: 2, trim: "Alpha", battery_kwh: null },
      { ...listing, id: 3, trim: "Bravo", battery_kwh: 58 },
    ];
    render(<ListingsTable items={batteryListings} filters={{}} onFilterChange={noop} onTagChange={noop} />);

    fireEvent.click(screen.getByRole("button", { name: "Sort by Battery" }));
    const order = rowTrims();
    expect(order[0]).toContain("Bravo"); // 58
    expect(order[1]).toContain("Charlie"); // 82
    expect(order[2]).toContain("Alpha"); // null, last
  });

  it("sorts by Distance with nulls last", () => {
    const distanceListings: Listing[] = [
      { ...listing, id: 1, trim: "Charlie", distance_km: 500 },
      { ...listing, id: 2, trim: "Alpha", distance_km: null },
      { ...listing, id: 3, trim: "Bravo", distance_km: 12 },
    ];
    render(<ListingsTable items={distanceListings} filters={{}} onFilterChange={noop} onTagChange={noop} />);

    fireEvent.click(screen.getByRole("button", { name: "Sort by Distance" }));
    const order = rowTrims();
    expect(order[0]).toContain("Bravo"); // 12
    expect(order[1]).toContain("Charlie"); // 500
    expect(order[2]).toContain("Alpha"); // null, last
  });
```

In `frontend/src/pages/Dashboard.test.tsx`, add the same two fields to its local `listing` fixture (after `power_kw: 150,`):

```tsx
const listing: Listing = {
  id: 1,
  source: "vw",
  source_id: "1",
  url: "https://example.com/1",
  model: "id4",
  trim: "Pro",
  price_eur: 30000,
  mileage_km: 1000,
  year: 2024,
  power_kw: 150,
  battery_kwh: null,
  condition: "used",
  location: "Berlin",
  distance_km: null,
  title: "VW ID.4 Pro",
  tag: null,
  status: "active",
  first_seen_at: "2026-08-11T00:00:00Z",
  last_seen_at: "2026-08-11T00:00:00Z",
};
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm run test`
Expected: FAIL — TypeScript errors (`battery_kwh`/`distance_km` don't exist on `Listing` yet) and the new rendering/sort assertions fail

- [ ] **Step 3: Add the fields, format helpers, and table columns**

In `frontend/src/types/index.ts`, update the `Listing` interface:

```typescript
export interface Listing {
  id: number;
  source: string;
  source_id: string;
  url: string;
  model: string;
  trim: string;
  price_eur: number | null;
  mileage_km: number | null;
  year: number | null;
  power_kw: number | null;
  battery_kwh: number | null;
  condition: string;
  location: string | null;
  distance_km: number | null;
  title: string;
  tag: string | null;
  status: string;
  first_seen_at: string;
  last_seen_at: string;
}
```

In `frontend/src/lib/format.ts`, add the two new formatters:

```typescript
const EUR = new Intl.NumberFormat("de-DE", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});
const NUM = new Intl.NumberFormat("de-DE");
const KWH = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 1 });
const KM_DISTANCE = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });

export function formatPrice(value: number | null): string {
  return value != null ? EUR.format(value) : "—";
}

export function formatKm(value: number | null): string {
  return value != null ? `${NUM.format(value)} km` : "—";
}

export function formatYear(value: number | null): string {
  return value != null ? String(value) : "—";
}

export function formatBatteryKwh(value: number | null): string {
  return value != null ? `${KWH.format(value)} kWh` : "—";
}

export function formatDistanceKm(value: number | null): string {
  return value != null ? `${KM_DISTANCE.format(value)} km` : "—";
}
```

In `frontend/src/components/ListingsTable.tsx`:

1. Update the import line to pull in the two new formatters:

```tsx
import { formatBatteryKwh, formatDistanceKm, formatKm, formatPrice, formatYear } from "../lib/format";
```

2. Extend `SortField` to include the two new columns:

```tsx
type SortField =
  | "model"
  | "trim"
  | "price_eur"
  | "mileage_km"
  | "year"
  | "power_kw"
  | "battery_kwh"
  | "condition"
  | "location"
  | "distance_km"
  | "source";
```

3. In the header `<tr>`, add `SortableHeader` for Battery (after Power, before Condition) and Distance (after Location, before Source):

```tsx
          <tr>
            <SortableHeader label="Model" field="model" sort={sort} onSort={onSort} />
            <SortableHeader label="Trim" field="trim" sort={sort} onSort={onSort} />
            <SortableHeader label="Price" field="price_eur" sort={sort} onSort={onSort} />
            <SortableHeader label="KM" field="mileage_km" sort={sort} onSort={onSort} />
            <SortableHeader label="Year" field="year" sort={sort} onSort={onSort} />
            <SortableHeader label="Power" field="power_kw" sort={sort} onSort={onSort} />
            <SortableHeader label="Battery" field="battery_kwh" sort={sort} onSort={onSort} />
            <SortableHeader label="Condition" field="condition" sort={sort} onSort={onSort} />
            <SortableHeader label="Location" field="location" sort={sort} onSort={onSort} />
            <SortableHeader label="Distance" field="distance_km" sort={sort} onSort={onSort} />
            <SortableHeader label="Source" field="source" sort={sort} onSort={onSort} />
            <th className="px-4 py-3 font-medium">Tag</th>
            <th className="px-4 py-3 font-medium" />
          </tr>
```

4. In the filter `<tr>`, add one blank `<th className="px-4 py-2" />` between the Power blank and the Condition blank, and another between the Location blank and the Source select, so the 13 filter cells line up with the 13 header cells:

```tsx
          <tr className="border-t border-slate-200 bg-white text-slate-600 normal-case tracking-normal">
            <th className="px-4 py-2">
              <select
                aria-label="Filter model"
                value={f.model ?? ""}
                onChange={(e) => set({ model: e.target.value || undefined })}
                className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-normal text-slate-700"
              >
                {MODEL_OPTIONS.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
            </th>
            <th className="px-4 py-2">
              <input
                type="text"
                aria-label="Filter trim"
                placeholder="contains, e.g. Pro"
                value={f.trim ?? ""}
                onChange={(e) => set({ trim: e.target.value || undefined })}
                className="w-32 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-normal text-slate-700"
              />
            </th>
            <th className="px-4 py-2">
              <input
                type="number"
                inputMode="numeric"
                aria-label="Max price"
                placeholder="max €"
                value={f.max_price ?? ""}
                onChange={(e) => set({ max_price: num(e.target.value) })}
                className="w-24 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-normal text-slate-700"
              />
            </th>
            <th className="px-4 py-2">
              <input
                type="number"
                inputMode="numeric"
                aria-label="Max km"
                placeholder="max km"
                value={f.max_km ?? ""}
                onChange={(e) => set({ max_km: num(e.target.value) })}
                className="w-24 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-normal text-slate-700"
              />
            </th>
            <th className="px-4 py-2" />
            <th className="px-4 py-2" />
            <th className="px-4 py-2" />
            <th className="px-4 py-2" />
            <th className="px-4 py-2" />
            <th className="px-4 py-2" />
            <th className="px-4 py-2">
              <select
                aria-label="Filter source"
                value={f.source ?? ""}
                onChange={(e) => set({ source: e.target.value || undefined })}
                className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-normal text-slate-700"
              >
                {SOURCE_OPTIONS.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </th>
            <th className="px-4 py-2" />
            <th className="px-4 py-2" />
          </tr>
```

5. Update `colSpan={11}` to `colSpan={13}` on the empty-state row:

```tsx
          {items.length === 0 ? (
            <tr>
              <td colSpan={13} className="px-4 py-12 text-center text-slate-500">
                No listings match these filters.
              </td>
            </tr>
```

6. In the data row, add a Battery `<td>` after Power and before Condition, and a Distance `<td>` after Location and before Source:

```tsx
                <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                  {l.power_kw != null ? `${l.power_kw} kW` : "—"}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-600">{formatBatteryKwh(l.battery_kwh)}</td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                  {CONDITION_LABEL[l.condition] ?? l.condition}
                </td>
                <td className="max-w-[12rem] px-4 py-3 text-slate-600">
                  <span className="line-clamp-1">{l.location ?? "—"}</span>
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-600">{formatDistanceKm(l.distance_km)}</td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-500">
                  {SOURCE_LABEL[l.source] ?? l.source}
                </td>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm run test`
Expected: PASS, full suite green

- [ ] **Step 5: Run the frontend build and typecheck**

Run: `cd frontend && npm run build`
Expected: builds cleanly with no TypeScript errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/format.ts \
  frontend/src/components/ListingsTable.tsx frontend/src/components/ListingsTable.test.tsx \
  frontend/src/pages/Dashboard.test.tsx
git commit -m "feat: add Battery and Distance columns to the listings table"
```

---

## Final verification

After Task 9, run the complete suite end-to-end before moving to deployment:

```bash
cd backend && uv run pytest -v
cd ../frontend && npm run test && npm run build
```

Then follow up with a real (non-mocked) manual check: `docker compose up --build` from the repo root, load the UI, click "Refresh" once, and confirm the Battery and Distance columns render and sort as expected against real scraped data (the first refresh will be slower than usual while it geocodes each new city — see the Global Constraints note on Nominatim throttling).
