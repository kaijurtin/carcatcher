# CarCatcher Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gut CarCatcher down to a single filterable table of VW ID.3/ID.4 listings scraped from AutoScout24 and VW.de, refreshed on demand, with no AI/scoring/saved-searches/Firecrawl.

**Architecture:** Same repo/deploy (FastAPI + SQLModel/SQLite backend, React/Vite frontend, LXC+docker-compose on CT113). Two source parsers (`AutoScout24Parser`, `VwDeParser`) implement a shared `Parser` interface and return `RawListing` rows; `crawl.py` upserts them into a single `Listing` table and marks missing rows `gone`. One API route pair (`GET /listings`, `POST /refresh`) backs a single-page frontend (filter bar + table + refresh button).

**Tech Stack:** Python 3.12+/FastAPI/SQLModel/httpx/BeautifulSoup/pytest/respx (backend); React/TS/Vite/Tailwind/Vitest/RTL (frontend).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-11-carcatcher-simplify-design.md` (read before starting — this plan implements it verbatim).
- All work happens on git branch `simplify-vw-id3-id4` (already created, spec commits already on it). Never commit to local `main`.
- No AI anywhere. No Firecrawl. No background scheduler — refresh is manual/synchronous only.
- Sources: `autoscout24`, `vw` only. `mobilede` is deferred (see spec) — do not implement it.
- Models: `id3`, `id4` only.
- DB: SQLite is dropped and recreated with the new schema on deploy (confirmed destructive, see spec's Deployment/migration section) — no migration of old rows.
- Commit after each task with a conventional-commit message; run the relevant test suite green before each commit.

---

## Task 1: Scraping foundation + AutoScout24 parser

**Files:**
- Create: `backend/carcatcher/scraping/base.py` (replaces existing content entirely)
- Create: `backend/carcatcher/scraping/autoscout24.py` (replaces existing content entirely)
- Test: `backend/tests/test_autoscout24.py` (replaces existing content entirely)
- Existing fixture reused as-is: `backend/tests/fixtures/autoscout24_search.html`

**Interfaces:**
- Produces: `Model = Literal["id3", "id4"]`; `RawListing` dataclass (fields: `source: str`, `source_id: str`, `url: str`, `model: Model`, `trim: str`, `price_eur: int | None`, `mileage_km: int | None`, `year: int | None`, `power_kw: int | None`, `condition: str`, `location: str | None`, `title: str`); `Parser` ABC with `name: str` and `fetch_listings(self, model: Model) -> list[RawListing]`. `AutoScout24Parser(Parser)` with `name = "autoscout24"`.
- Also produces (module-level, used directly by tests and by Task 3's registry): `parse_search_html(html: str, model: Model) -> list[RawListing]`, `build_search_url(model: Model, page: int) -> str`.

- [ ] **Step 1: Write `base.py`**

```python
"""Parser interface: turn a model search into unified RawListing rows."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

Model = Literal["id3", "id4"]


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
    condition: str  # "new" | "used"
    location: str | None
    title: str


class Parser(ABC):
    """One source (autoscout24, vw, …)."""

    name: str

    @abstractmethod
    def fetch_listings(self, model: Model) -> list[RawListing]:
        """Fetch and parse every listing for `model` from this source."""
        ...
```

- [ ] **Step 2: Inspect the real fixture to confirm field values (sanity check before writing tests)**

Run: `cd backend && .venv/bin/python -c "
from bs4 import BeautifulSoup
import json
html = open('tests/fixtures/autoscout24_search.html', encoding='utf-8').read()
data = json.loads(BeautifulSoup(html, 'html.parser').find('script', id='__NEXT_DATA__').string)
print(json.dumps(data['props']['pageProps']['listings'][0], indent=2, ensure_ascii=False)[:1500])
"`

Expected: first listing is the BMW X3 fixture entry with `vehicle.offerType: "U"`, `vehicle.modelVersionInput: "xDrive20d Aut. Mild-Hybrid"`, `price.priceFormatted: "€ 25.000"`, `vehicleDetails` containing `mileage_odometer: "53.063 km"`, `calendar: "02/2024"`, `speedometer: "140 kW (190 PS)"`, `location: {"zip": "71154", "city": "Nufringen"}`, `url` containing UUID `883482c0-d08c-45f2-b997-abcd14487f9b`. (Confirmed live 2026-08-11 — this step is a guard against fixture drift, not exploratory.)

- [ ] **Step 3: Write the failing test file `backend/tests/test_autoscout24.py`**

```python
"""AutoScout24 parser tests against the committed real __NEXT_DATA__ fixture."""

from __future__ import annotations

from pathlib import Path

import httpx
import respx

from carcatcher.scraping.autoscout24 import (
    AutoScout24Parser,
    build_search_url,
    parse_search_html,
)

FIXTURE = Path(__file__).parent / "fixtures" / "autoscout24_search.html"


def _html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parses_next_data_listings():
    listings = parse_search_html(_html(), "id4")
    assert len(listings) == 3
    assert all(l.source == "autoscout24" for l in listings)
    assert all(l.model == "id4" for l in listings)
    assert all(l.url.startswith("https://www.autoscout24.de/") for l in listings)


def test_structured_fields_populated():
    listings = parse_search_html(_html(), "id4")
    bmw = listings[0]
    assert bmw.trim == "xDrive20d Aut. Mild-Hybrid"
    assert bmw.price_eur == 25000
    assert bmw.mileage_km == 53063
    assert bmw.year == 2024
    assert bmw.power_kw == 140
    assert bmw.condition == "used"
    assert bmw.location == "71154 Nufringen"
    assert bmw.source_id == "883482c0-d08c-45f2-b997-abcd14487f9b"


def test_returns_empty_list_for_html_without_next_data():
    assert parse_search_html("<html><body>no data here</body></html>", "id4") == []


def test_build_search_url_id4():
    url = build_search_url("id4", page=2)
    assert url == (
        "https://www.autoscout24.de/lst/volkswagen/id-4"
        "?atype=C&cy=D&sort=standard&desc=0&page=2&size=20"
    )


def test_build_search_url_id3():
    url = build_search_url("id3", page=1)
    assert "/lst/volkswagen/id-3?" in url


@respx.mock
def test_fetch_listings_paginates_until_an_empty_page():
    respx.get(build_search_url("id4", 1)).mock(return_value=httpx.Response(200, text=_html()))
    respx.get(build_search_url("id4", 2)).mock(
        return_value=httpx.Response(200, text="<html></html>")
    )
    parser = AutoScout24Parser()
    listings = parser.fetch_listings("id4")
    assert len(listings) == 3
```

- [ ] **Step 4: Run the test to verify it fails (module doesn't exist yet)**

Run: `cd backend && .venv/bin/pytest tests/test_autoscout24.py -v`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'carcatcher.scraping.autoscout24'` (the old file still has the pre-simplify content at this point, whose exports don't match — either way the test fails).

- [ ] **Step 5: Replace `backend/carcatcher/scraping/autoscout24.py` entirely**

```python
"""AutoScout24.de parser (source: "autoscout24").

Plain HTTP GET — no rendering needed. AS24 is a Next.js app that embeds its search
results as a `<script id="__NEXT_DATA__">` JSON blob in the initial server-rendered
HTML (verified live 2026-08-11: a plain `curl` with a browser-like User-Agent
returns it directly, no headless browser required).
"""

from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

from carcatcher.scraping.base import Model, Parser, RawListing

SOURCE = "autoscout24"
BASE_URL = "https://www.autoscout24.de"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

_MODEL_SLUGS: dict[Model, str] = {"id3": "id-3", "id4": "id-4"}
_DIGITS_RE = re.compile(r"\d[\d.]*")
_UUID_RE = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")
_POWER_RE = re.compile(r"(\d+)\s*kW")
_YEAR_RE = re.compile(r"(\d{4})")


def _to_int(text: str | None) -> int | None:
    if not text:
        return None
    m = _DIGITS_RE.search(text)
    if not m:
        return None
    digits = m.group(0).replace(".", "")
    return int(digits) if digits.isdigit() else None


def _details(vehicle_details: list) -> dict:
    out: dict = {}
    for d in vehicle_details or []:
        icon, value = d.get("iconName"), d.get("data")
        if icon == "mileage_odometer":
            out["mileage_km"] = _to_int(value)
        elif icon == "calendar":
            m = _YEAR_RE.search(value or "")
            out["year"] = int(m.group(1)) if m else None
        elif icon == "speedometer":
            m = _POWER_RE.search(value or "")
            out["power_kw"] = int(m.group(1)) if m else None
    return out


def _source_id(url: str) -> str:
    m = _UUID_RE.search(url)
    return m.group(1) if m else url.rstrip("/").rsplit("/", 1)[-1]


def _condition(vehicle: dict) -> str:
    return "new" if (vehicle.get("offerType") or "").strip().upper() == "N" else "used"


def _item_to_listing(item: dict, model: Model) -> RawListing | None:
    if not item.get("id"):
        return None
    vehicle = item.get("vehicle") or {}
    url = item.get("url") or ""
    url = url if url.startswith("http") else f"{BASE_URL}{url}"
    details = _details(item.get("vehicleDetails") or [])
    loc = item.get("location") or {}
    return RawListing(
        source=SOURCE,
        source_id=_source_id(url),
        url=url,
        model=model,
        trim=vehicle.get("modelVersionInput") or vehicle.get("subtitle") or "",
        price_eur=_to_int((item.get("price") or {}).get("priceFormatted")),
        mileage_km=details.get("mileage_km"),
        year=details.get("year"),
        power_kw=details.get("power_kw"),
        condition=_condition(vehicle),
        location=" ".join(p for p in (loc.get("zip"), loc.get("city")) if p) or None,
        title=" ".join(
            p for p in (vehicle.get("make"), vehicle.get("model"), vehicle.get("modelVersionInput"))
            if p
        ),
    )


def parse_search_html(html: str, model: Model) -> list[RawListing]:
    soup = BeautifulSoup(html, "html.parser")
    node = soup.find("script", id="__NEXT_DATA__")
    if node is None or not node.string:
        return []
    try:
        import json

        data = json.loads(node.string)
    except ValueError:
        return []
    items = data.get("props", {}).get("pageProps", {}).get("listings", []) or []
    out = [_item_to_listing(item, model) for item in items]
    return [l for l in out if l is not None]


def build_search_url(model: Model, page: int) -> str:
    slug = _MODEL_SLUGS[model]
    params = "&".join(["atype=C", "cy=D", "sort=standard", "desc=0", f"page={page}", "size=20"])
    return f"{BASE_URL}/lst/volkswagen/{slug}?{params}"


class AutoScout24Parser(Parser):
    name = SOURCE

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=20.0, headers={"User-Agent": USER_AGENT})

    def fetch_listings(self, model: Model) -> list[RawListing]:
        results: list[RawListing] = []
        for page in range(1, 6):  # AS24 pages ~20/each; 5 pages covers this source's v1 volume
            resp = self._client.get(build_search_url(model, page))
            resp.raise_for_status()
            page_listings = parse_search_html(resp.text, model)
            if not page_listings:
                break
            results.extend(page_listings)
        return results
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_autoscout24.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 7: Commit**

```bash
cd /root/repos/carcatcher
git add backend/carcatcher/scraping/base.py backend/carcatcher/scraping/autoscout24.py backend/tests/test_autoscout24.py
git commit -m "feat: rewrite scraping base + AutoScout24 parser for direct HTTP, no Firecrawl/AI"
```

---

## Task 2: VW.de parser

**Files:**
- Create: `backend/carcatcher/scraping/vwde.py`
- Create: `backend/tests/fixtures/vwde_search.json` (already written to disk during planning research — verify it's present, `git add` it in this task)
- Test: `backend/tests/test_vwde.py`

**Interfaces:**
- Consumes: `Model`, `Parser`, `RawListing` from `carcatcher.scraping.base` (Task 1).
- Produces: `VwDeParser(Parser)` with `name = "vw"`; `parse_search_response(data: dict, model: Model) -> list[RawListing]`; `build_params(model: Model, page: int) -> dict`; `VwDeError(RuntimeError)`.

- [ ] **Step 1: Verify the fixture is present and valid**

Run: `python3 -m json.tool backend/tests/fixtures/vwde_search.json > /dev/null && echo OK`
Expected: `OK`. This fixture is a trimmed real response from `https://v3-120-0.gsl.feature-app.io/bff/car/search` (captured live 2026-08-11, verified working from a fresh cookie-less request), containing 4 cars — 3 real `"Junge Gebrauchtwagen"` (used) entries plus one hand-added `cartype.code: "N"` (new) entry to cover the condition-mapping branch.

- [ ] **Step 2: Write the failing test file `backend/tests/test_vwde.py`**

```python
"""VW.de parser tests against a trimmed real API response fixture."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from carcatcher.scraping.vwde import (
    VwDeError,
    VwDeParser,
    build_params,
    parse_search_response,
)

FIXTURE = Path(__file__).parent / "fixtures" / "vwde_search.json"
API_URL = "https://v3-120-0.gsl.feature-app.io/bff/car/search"


def _data() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_parses_all_cars():
    listings = parse_search_response(_data(), "id4")
    assert len(listings) == 4
    assert all(l.source == "vw" for l in listings)
    assert all(l.model == "id4" for l in listings)


def test_fields_mapped_correctly():
    listings = parse_search_response(_data(), "id4")
    first = listings[0]
    assert first.source_id == "DEU4385118916-34"
    assert first.trim == "ID.4 Pure 2,49% WÄRMEPU NAV 5J-GAR MATRIX APP 19"
    assert first.price_eur == 34410
    assert first.mileage_km == 10937
    assert first.year == 2025
    assert first.power_kw == 125
    assert first.condition == "used"
    assert first.location == "Kölln-Reisiek"
    assert first.url == (
        "https://www.volkswagen.de/de/modelle/verfuegbare-fahrzeuge-suche.html"
        "/__app/search/car/REVVNDM4NTExODkxNi0zNA=.app"
    )


def test_new_car_condition_mapped():
    listings = parse_search_response(_data(), "id4")
    gtx = next(l for l in listings if l.source_id == "DEU12345000-01")
    assert gtx.condition == "new"


def test_unexpected_response_shape_raises():
    with pytest.raises(VwDeError):
        parse_search_response({"unexpected": True}, "id4")


def test_build_params_selects_model_code():
    assert build_params("id4", page=1)["t_model"] == "BQIE"
    assert build_params("id3", page=1)["t_model"] == "BQID"
    assert build_params("id4", page=1)["t_manuf"] == "BQ"


@respx.mock
def test_fetch_listings_paginates_using_page_max():
    page1 = _data()
    page1["meta"]["pageMax"] = 2
    page2 = {"meta": {"pageMax": 2}, "cars": []}
    respx.get(API_URL).mock(
        side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2)]
    )
    parser = VwDeParser()
    listings = parser.fetch_listings("id4")
    assert len(listings) == 4
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_vwde.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'carcatcher.scraping.vwde'`.

- [ ] **Step 4: Write `backend/carcatcher/scraping/vwde.py`**

```python
"""VW.de parser (source: "vw").

Volkswagen's own official used/new-car search. The public search page
(volkswagen.de/.../verfuegbare-fahrzeuge-suche.html) is a client-hydrated React app
with no listing data in its initial HTML; the actual data comes from a JSON API the
page calls, verified live 2026-08-11 to work over plain HTTP with no browser and no
session/cookies required (a fresh, cookie-less request succeeds).
"""

from __future__ import annotations

import re

import httpx

from carcatcher.scraping.base import Model, Parser, RawListing

SOURCE = "vw"
API_URL = "https://v3-120-0.gsl.feature-app.io/bff/car/search"
DETAIL_URL = (
    "https://www.volkswagen.de/de/modelle/verfuegbare-fahrzeuge-suche.html"
    "/__app/search/car/{key}.app"
)

_MODEL_CODES: dict[Model, str] = {"id3": "BQID", "id4": "BQIE"}

# Static per-deploy credentials for VW's onehub_pkw "publish" feature-app config,
# verified live 2026-08-11 to work from a fresh, cookie-less request (not
# session-bound). If VW redeploys and rotates `dataVersion`, calls will start
# failing loudly (see `parse_search_response`) rather than silently returning
# nothing — that's the signal a credential refresh is needed.
_STATIC_PARAMS = {
    "country": "DE",
    "language": "de",
    "market": "passenger",
    "oneapiKey": "nOqkwPxxu8ViK9aaHvTkglzVZAlX4yIx",
    "dataVersion": "B62F538267A27D9C9B1AC0E02FF3688F",
    "endpoint": (
        '{"endpoint":{"type":"publish","country":"de","language":"de",'
        '"content":"onehub_pkw","envName":"prod","testScenarioId":null},'
        '"signature":"eXxF3Vp4siIxU67pK2Vs14eGqdMbD0HzeFcn3b058j8="}'
    ),
}

_POWER_RE = re.compile(r"(\d+)\s*kW")
_YEAR_RE = re.compile(r"(\d{4})")


class VwDeError(RuntimeError):
    """Raised when VW's API responds with an unexpected shape (e.g. rotated credentials)."""


def _power_kw(label: str | None) -> int | None:
    if not label:
        return None
    m = _POWER_RE.search(label)
    return int(m.group(1)) if m else None


def _condition(car: dict) -> str:
    code = (car.get("cartype") or {}).get("code")
    return "new" if code == "N" else "used"


def _car_to_listing(car: dict, model: Model) -> RawListing | None:
    carid = car.get("carid")
    key = car.get("key")
    if not carid or not key:
        return None
    price = (car.get("parsedPrice") or {}).get("value")
    mileage = (car.get("mileage") or {}).get("raw_value")
    year_match = _YEAR_RE.match(car.get("initialreg") or "")
    dealer_city = ((car.get("dealer") or {}).get("city") or {}).get("value")
    return RawListing(
        source=SOURCE,
        source_id=str(carid),
        url=DETAIL_URL.format(key=key),
        model=model,
        trim=(car.get("subtitle") or {}).get("value") or car.get("title") or "",
        price_eur=int(price) if price is not None else None,
        mileage_km=int(mileage) if mileage is not None else None,
        year=int(year_match.group(1)) if year_match else None,
        power_kw=_power_kw(car.get("powerLabel")),
        condition=_condition(car),
        location=dealer_city,
        title=car.get("title") or "",
    )


def parse_search_response(data: dict, model: Model) -> list[RawListing]:
    if "cars" not in data or "meta" not in data:
        raise VwDeError(f"unexpected VW search response shape: keys={list(data.keys())}")
    cars = data.get("cars") or []
    out = [_car_to_listing(car, model) for car in cars]
    return [l for l in out if l is not None]


def build_params(model: Model, page: int) -> dict:
    return {
        **_STATIC_PARAMS,
        "t_manuf": "BQ",
        "t_model": _MODEL_CODES[model],
        "sort": "DATE_OFFER",
        "sortdirection": "DESC",
        "pageitems": 12,
        "page": page,
    }


class VwDeParser(Parser):
    name = SOURCE

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=20.0)

    def fetch_listings(self, model: Model) -> list[RawListing]:
        results: list[RawListing] = []
        page = 1
        page_max = 1
        while page <= page_max:
            resp = self._client.get(API_URL, params=build_params(model, page))
            resp.raise_for_status()
            data = resp.json()
            results.extend(parse_search_response(data, model))
            page_max = (data.get("meta") or {}).get("pageMax", page)
            page += 1
        return results
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_vwde.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /root/repos/carcatcher
git add backend/carcatcher/scraping/vwde.py backend/tests/test_vwde.py backend/tests/fixtures/vwde_search.json
git commit -m "feat: add VW.de parser hitting the site's own JSON search API directly"
```

---

## Task 3: Registry + delete dead scraper files

**Files:**
- Create: `backend/carcatcher/scraping/registry.py` (replaces existing content)
- Delete: `backend/carcatcher/scraping/kleinanzeigen.py`
- Delete: `backend/carcatcher/scraping/mobilede.py`
- Delete: `backend/carcatcher/scraping/firecrawl_client.py`
- Delete: `backend/tests/test_kleinanzeigen.py`
- Delete: `backend/tests/test_firecrawl_client.py`
- Delete: `backend/tests/test_mobilede.py` (added by Amendment 3 below — a gap in the original plan)
- Delete: `backend/tests/fixtures/kleinanzeigen_search.html`
- Delete: `backend/tests/fixtures/mobilede_search.html`
- Modify: `backend/tests/conftest.py` — make the `client` fixture's `create_app` import lazy (see Amendment 3)
- Test: `backend/tests/test_registry.py` (new, small)

**Interfaces:**
- Consumes: `AutoScout24Parser` (Task 1), `VwDeParser` (Task 2), `Parser` (Task 1).
- Produces: `build_registry() -> dict[str, Parser]` — used by Task 6's `app_state.py`.

**Amendment 1 (added after Task 1's review):** Task 1 discovered that `base.py` cannot be fully stripped to just `Model`/`RawListing`/`Parser` without breaking `conftest.py`'s module-level import of `carcatcher.main.create_app` — which transitively imports `kleinanzeigen.py`/`mobilede.py`, and those do `from carcatcher.scraping.base import ListingStub, RawPage, Scraper`. Task 1 therefore left a clearly-banner-commented `# DEPRECATED` shim (`ListingStub`, `RawPage`, `Scraper`, `sha256_text` in `base.py`; an `AutoScout24Scraper = AutoScout24Parser` alias in `autoscout24.py`) as a necessary transitional measure.

**Amendment 3 (added after Task 3's implementer hit a second, broader blocker):** Even with Amendment 2's correction (shim stays until Task 7), this task still couldn't pass its own acceptance test. Root cause, confirmed by direct investigation: `carcatcher/app_state.py` (not rewritten until Task 6) does `from carcatcher.scraping.firecrawl_client import FirecrawlClient` **at module level** — and this task deletes `firecrawl_client.py`. Since `conftest.py` does `from carcatcher.main import create_app` at module level too, and `main.py` → `app_state.py` → `firecrawl_client` is a straight import chain, deleting `firecrawl_client.py` breaks `conftest.py`'s own import, which aborts test collection for the *entire* `tests/` directory — not just this task's tests. This is a structural issue that will recur: Task 4 has the same shape (old `routes/listings.py`, not rewritten until Task 6, imports model names Task 4 deletes from `db/models.py`).

**The general fix, applied now rather than patched per-task:** `conftest.py`'s `client` fixture currently does `from carcatcher.main import create_app` at module level (line 13). Move that import to be local to the `client()` fixture function body instead. This decouples "can pytest collect and run tests that don't need the full app" from "does the full app currently import cleanly" — tests that request the `client`/`test_engine` fixtures still need a working app (none do until Task 6 anyway), but standalone unit tests like `test_registry.py`/`test_autoscout24.py`/`test_vwde.py` no longer get collateral-damaged by an unrelated, not-yet-migrated module. Task 7's Step 3 (full `conftest.py` rewrite) is unaffected — by Task 7, `main.py`/`app_state.py` are already fully migrated (Task 6 done), so the import being eager or lazy no longer matters there; keep Task 7's conftest.py as already written in this plan.

Also found in the same investigation: `backend/tests/test_mobilede.py` exists and was never scheduled for deletion anywhere in this plan — a gap from the original design. It tests the old `mobilede.py` (deleted by this task), so it must be deleted here too, alongside `test_kleinanzeigen.py`.

**Amendment 2 (added after Task 3's implementer hit a blocker — supersedes Amendment 1's removal plan):** Amendment 1 assumed this task (Task 3) could delete the shim once `kleinanzeigen.py`/`mobilede.py` are gone. That's wrong: a grep across the whole backend (`grep -rln --include='*.py' -E '\b(ListingStub|RawPage|Scraper|sha256_text|AutoScout24Scraper)\b' carcatcher tests`) found **two more consumers** neither Task 1 nor the original Task 3 plan accounted for: `carcatcher/app_state.py` (imports `Scraper` for a type annotation — fixed when Task 6 rewrites this file) and `carcatcher/pipeline/run.py` + `backend/tests/test_multisource.py` (both use `ListingStub`/`Scraper`/`sha256_text`/`AutoScout24Scraper` throughout — both deleted whole in **Task 7**, not this task). **This task does NOT remove the shim.** It stays in place, banner-commented as deprecated, until Task 7 — see Task 7's amendment below for the actual removal step. This task only does the registry rewrite and the `kleinanzeigen.py`/`mobilede.py`/`firecrawl_client.py` deletions below.

- [ ] **Step 1: Write the failing test `backend/tests/test_registry.py`**

```python
"""Registry wiring: both v1 sources are registered under their source name."""

from __future__ import annotations

from carcatcher.scraping.autoscout24 import AutoScout24Parser
from carcatcher.scraping.registry import build_registry
from carcatcher.scraping.vwde import VwDeParser


def test_registry_has_both_v1_sources():
    registry = build_registry()
    assert set(registry.keys()) == {"autoscout24", "vw"}
    assert isinstance(registry["autoscout24"], AutoScout24Parser)
    assert isinstance(registry["vw"], VwDeParser)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_registry.py -v`
Expected: FAIL — `registry.py` still imports the now-broken `KleinanzeigenScraper`/`MobileDeScraper`/`FirecrawlClient` and will error on import.

- [ ] **Step 3: Replace `backend/carcatcher/scraping/registry.py` entirely**

```python
"""Parser registry: source name -> Parser instance."""

from __future__ import annotations

from carcatcher.scraping.autoscout24 import AutoScout24Parser
from carcatcher.scraping.base import Parser
from carcatcher.scraping.vwde import VwDeParser


def build_registry() -> dict[str, Parser]:
    parsers: list[Parser] = [AutoScout24Parser(), VwDeParser()]
    return {p.name: p for p in parsers}
```

- [ ] **Step 4: Delete the dead scraper files, their tests, and their fixtures**

```bash
cd /root/repos/carcatcher
git rm backend/carcatcher/scraping/kleinanzeigen.py \
       backend/carcatcher/scraping/mobilede.py \
       backend/carcatcher/scraping/firecrawl_client.py \
       backend/tests/test_kleinanzeigen.py \
       backend/tests/test_firecrawl_client.py \
       backend/tests/test_mobilede.py \
       backend/tests/fixtures/kleinanzeigen_search.html \
       backend/tests/fixtures/mobilede_search.html
```

- [ ] **Step 4b: Make `conftest.py`'s `client` fixture import `create_app` lazily**

This is the fix described in Amendment 3 above. In `backend/tests/conftest.py`, remove the module-level line `from carcatcher.main import create_app`, and add `from carcatcher.main import create_app` as the first line inside the `client()` fixture function body instead. Nothing else in the file changes. Resulting fixture:

```python
@pytest.fixture()
def client(test_engine):
    from carcatcher.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c
```

- [ ] **Step 5: Run to verify the registry test passes** (do NOT run the full suite — `pipeline/run.py` and its tests are still on the old `Scraper` interface until Task 7, so a full-suite run will show pre-existing unrelated failures; that's expected)

Run: `cd backend && .venv/bin/pytest tests/test_registry.py tests/test_autoscout24.py tests/test_vwde.py -v`
Expected: all PASS — and collection no longer aborts even though `carcatcher.main`'s import chain is still broken (`app_state.py` still imports the now-deleted `firecrawl_client`), because nothing in these three test files requests the `client`/`test_engine` fixtures that would trigger that import.

- [ ] **Step 6: Commit**

```bash
cd /root/repos/carcatcher
git add backend/carcatcher/scraping/registry.py backend/tests/test_registry.py backend/tests/conftest.py
git commit -m "feat: rewrite scraper registry for 2-source v1; delete Kleinanzeigen/mobile.de/Firecrawl; make conftest's app import lazy"
```

---

## Task 4: DB model rewrite + engine cleanup

**Files:**
- Create: `backend/carcatcher/db/models.py` (replaces existing content entirely)
- Modify: `backend/carcatcher/db/engine.py` — remove `_ADDED_COLUMNS`/`_ensure_added_columns`
- Test: `backend/tests/test_db_models.py` (new, small)
- Delete: `backend/tests/test_db_migrate.py` (tested the now-deleted `_ensure_added_columns` migration)

**Interfaces:**
- Produces: `ListingStatus(str, enum.Enum)` with `ACTIVE = "active"`, `GONE = "gone"`; `Listing(SQLModel, table=True)` with fields `id, source, source_id, url, model, trim, price_eur, mileage_km, year, power_kw, condition, location, title, status, first_seen_at, last_seen_at` and `UniqueConstraint("source", "source_id")`. Used by Task 5 (`crawl.py`) and Task 6 (API routes).

- [ ] **Step 1: Write the failing test `backend/tests/test_db_models.py`**

```python
"""DB schema smoke test: the simplified Listing table creates cleanly and enforces
the (source, source_id) uniqueness the crawl upsert relies on."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from carcatcher.db.models import Listing, ListingStatus


def _engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


def test_creates_and_reads_a_listing():
    engine = _engine()
    with Session(engine) as session:
        session.add(
            Listing(
                source="vw", source_id="1", url="https://x/1", model="id4", trim="Pro",
                price_eur=30000, mileage_km=1000, year=2024, power_kw=150,
                condition="used", location="Berlin", title="VW ID.4 Pro",
            )
        )
        session.commit()
        row = session.exec(
            __import__("sqlmodel").select(Listing).where(Listing.source_id == "1")
        ).one()
        assert row.status == ListingStatus.ACTIVE.value


def test_enforces_source_source_id_uniqueness():
    engine = _engine()
    with Session(engine) as session:
        session.add(Listing(source="vw", source_id="1", url="https://x/1", model="id4", title="A"))
        session.commit()
        session.add(Listing(source="vw", source_id="1", url="https://x/1-dup", model="id4", title="B"))
        with pytest.raises(IntegrityError):
            session.commit()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_db_models.py -v`
Expected: FAIL — current `models.py` has a much larger `Listing` with different required fields and no bare `condition`/`price_eur`/`trim` columns.

- [ ] **Step 3: Replace `backend/carcatcher/db/models.py` entirely**

```python
"""SQLModel tables for CarCatcher.

Snapshot semantics: listings are upserted by (source, source_id) on every crawl.
A listing not seen in a successful crawl of its own source is marked `gone`. There
is no price history — the current set of `active` rows IS the snapshot.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Timezone-aware UTC now (avoids deprecated datetime.utcnow)."""
    return datetime.now(timezone.utc)


class ListingStatus(str, enum.Enum):
    ACTIVE = "active"
    GONE = "gone"


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
    condition: str = "used"  # "new" | "used"
    location: str | None = None
    title: str = ""

    status: str = Field(default=ListingStatus.ACTIVE.value, index=True)
    first_seen_at: datetime = Field(default_factory=utcnow)
    last_seen_at: datetime = Field(default_factory=utcnow, index=True)
```

- [ ] **Step 4: Run to verify the new test passes**

Run: `cd backend && .venv/bin/pytest tests/test_db_models.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Remove the now-dead column-migration machinery from `backend/carcatcher/db/engine.py`**

Delete lines 43-69 (the `_ADDED_COLUMNS` dict and `_ensure_added_columns` function) and the call to it in `init_db`:

```python
# Remove this whole block:
# _ADDED_COLUMNS: dict[str, dict[str, str]] = {...}
# def _ensure_added_columns(engine: Engine) -> None: ...
```

Replace `init_db`:

```python
def init_db() -> None:
    """Create all tables if they do not yet exist."""
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
```

- [ ] **Step 6: Delete the now-irrelevant migration test**

```bash
cd /root/repos/carcatcher
git rm backend/tests/test_db_migrate.py
```

- [ ] **Step 7: Run the full backend suite to check nothing else references the deleted migration code**

Run: `cd backend && .venv/bin/pytest -v 2>&1 | tail -40`
Expected: failures are expected at this point from files not yet updated in later tasks (routes, pipeline, etc. still reference the old `Listing` shape) — confirm the only NEW failures introduced here are import errors mentioning fields/modules this task intentionally removed (`battery_kwh`, `ai_evaluation`, `SavedSearch`, `_ensure_added_columns`, etc.), not unrelated breakage. `test_db_models.py` and `test_registry.py` and `test_autoscout24.py`/`test_vwde.py` should be green.

- [ ] **Step 8: Commit**

```bash
cd /root/repos/carcatcher
git add backend/carcatcher/db/models.py backend/carcatcher/db/engine.py backend/tests/test_db_models.py
git commit -m "feat: replace Listing schema with the simplified single-table model"
```

---

## Task 5: Crawl orchestration (`crawl.py`)

**Files:**
- Create: `backend/carcatcher/crawl.py`
- Test: `backend/tests/test_crawl.py`

**Interfaces:**
- Consumes: `Listing`, `ListingStatus` (Task 4); `Model`, `Parser`, `RawListing` (Task 1).
- Produces: `CrawlSummary` dataclass (`added: int`, `updated: int`, `gone: int`, `failed_sources: list[str]`, `refreshed_at: datetime`); `run_crawl(session: Session, parsers: dict[str, Parser]) -> CrawlSummary`; `MODELS: tuple[Model, ...]`. Used by Task 6's `refresh.py` route.

- [ ] **Step 1: Write the failing test `backend/tests/test_crawl.py`**

```python
"""Tests for crawl orchestration: upsert + gone-marking + partial-failure handling."""

from __future__ import annotations

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from carcatcher.crawl import run_crawl
from carcatcher.db.models import Listing, ListingStatus
from carcatcher.scraping.base import RawListing


def _engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


class FakeParser:
    def __init__(self, name, by_model):
        self.name = name
        self._by_model = by_model

    def fetch_listings(self, model):
        return self._by_model.get(model, [])


class FailingParser:
    name = "broken"

    def fetch_listings(self, model):
        raise RuntimeError("boom")


def _raw(source, source_id, model="id4", price=30000):
    return RawListing(
        source=source, source_id=source_id, url=f"https://x/{source_id}",
        model=model, trim="Pro", price_eur=price, mileage_km=1000, year=2024,
        power_kw=150, condition="used", location="Berlin", title="VW ID.4 Pro",
    )


def test_first_crawl_inserts_new_listings():
    engine = _engine()
    parsers = {"vw": FakeParser("vw", {"id4": [_raw("vw", "1")], "id3": []})}
    with Session(engine) as session:
        summary = run_crawl(session, parsers)
        assert summary.added == 1
        assert summary.updated == 0
        rows = session.exec(select(Listing)).all()
        assert len(rows) == 1
        assert rows[0].status == ListingStatus.ACTIVE.value


def test_second_crawl_updates_existing_and_marks_missing_gone():
    engine = _engine()
    with Session(engine) as session:
        run_crawl(
            session,
            {"vw": FakeParser("vw", {"id4": [_raw("vw", "1"), _raw("vw", "2")], "id3": []})},
        )

    with Session(engine) as session:
        # listing "2" disappears, listing "1" reappears with a new price
        summary = run_crawl(
            session,
            {"vw": FakeParser("vw", {"id4": [_raw("vw", "1", price=29000)], "id3": []})},
        )
        assert summary.updated == 1
        assert summary.gone == 1
        rows = {r.source_id: r for r in session.exec(select(Listing)).all()}
        assert rows["1"].status == ListingStatus.ACTIVE.value
        assert rows["1"].price_eur == 29000
        assert rows["2"].status == ListingStatus.GONE.value


def test_failed_source_does_not_mark_its_listings_gone():
    engine = _engine()
    with Session(engine) as session:
        run_crawl(session, {"vw": FakeParser("vw", {"id4": [_raw("vw", "1")], "id3": []})})

    with Session(engine) as session:
        summary = run_crawl(session, {"vw": FailingParser()})
        assert summary.failed_sources == ["vw"]
        assert summary.gone == 0
        row = session.exec(select(Listing).where(Listing.source_id == "1")).one()
        assert row.status == ListingStatus.ACTIVE.value


def test_one_source_failing_does_not_stop_another_source_succeeding():
    engine = _engine()
    parsers = {
        "vw": FailingParser(),
        "autoscout24": FakeParser("autoscout24", {"id4": [_raw("autoscout24", "9")], "id3": []}),
    }
    with Session(engine) as session:
        summary = run_crawl(session, parsers)
        assert summary.added == 1
        assert summary.failed_sources == ["vw"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_crawl.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'carcatcher.crawl'`.

- [ ] **Step 3: Write `backend/carcatcher/crawl.py`**

```python
"""Crawl orchestration: fetch every source x model, upsert into `Listing`, mark
listings that disappeared from a successfully-crawled source as `gone`."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlmodel import Session, select

from carcatcher.db.models import Listing, ListingStatus
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


def run_crawl(session: Session, parsers: dict[str, Parser]) -> CrawlSummary:
    summary = CrawlSummary()
    seen_keys: set[tuple[str, str]] = set()
    succeeded_sources: set[str] = set()

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
                if _upsert(session, raw):
                    summary.added += 1
                else:
                    summary.updated += 1
        if source_ok:
            succeeded_sources.add(name)

    summary.gone = _mark_gone(session, succeeded_sources, seen_keys)
    session.commit()
    return summary


def _upsert(session: Session, raw: RawListing) -> bool:
    """Insert or update the `Listing` row for `raw`. Returns True if newly inserted."""
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
        existing.condition = raw.condition
        existing.location = raw.location
        existing.title = raw.title
        existing.status = ListingStatus.ACTIVE.value
        existing.last_seen_at = now
        session.add(existing)
        return False
    session.add(
        Listing(
            source=raw.source, source_id=raw.source_id, url=raw.url, model=raw.model,
            trim=raw.trim, price_eur=raw.price_eur, mileage_km=raw.mileage_km,
            year=raw.year, power_kw=raw.power_kw, condition=raw.condition,
            location=raw.location, title=raw.title, status=ListingStatus.ACTIVE.value,
            first_seen_at=now, last_seen_at=now,
        )
    )
    return True


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

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_crawl.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /root/repos/carcatcher
git add backend/carcatcher/crawl.py backend/tests/test_crawl.py
git commit -m "feat: add crawl orchestration — upsert, gone-marking, partial-failure handling"
```

---

## Task 6: API routes, app state, main, config

**Files:**
- Create: `backend/carcatcher/api/routes/listings.py` (replaces existing content entirely)
- Create: `backend/carcatcher/api/routes/refresh.py` (replaces existing content entirely)
- Create: `backend/carcatcher/app_state.py` (replaces existing content entirely)
- Create: `backend/carcatcher/main.py` (replaces existing content entirely)
- Create: `backend/carcatcher/config.py` (replaces existing content entirely)
- Delete: `backend/carcatcher/schemas.py`
- Delete: `backend/carcatcher/api/routes/recommend.py`, `saved_searches.py`, `search.py`, `settings.py`, `models.py`
- Test: `backend/tests/test_api_listings.py` (replaces existing content entirely)
- Test: `backend/tests/test_api_refresh.py` (replaces existing content entirely)
- `backend/tests/test_api_health.py` — unchanged, no edits needed (verify it still passes at the end of this task)

**Interfaces:**
- Consumes: `Listing`, `ListingStatus` (Task 4); `run_crawl`, `CrawlSummary` (Task 5); `build_registry` (Task 3).
- Produces: `AppState` dataclass (`parsers: dict[str, Parser]`); `build_state()`, `set_state()`, `get_state()`; `create_app()`; FastAPI routers mounted at `/api/listings` (`GET`) and `/api/refresh` (`POST`).

- [ ] **Step 1: Write the failing test `backend/tests/test_api_listings.py`**

```python
"""Tests for GET /api/listings filtering."""

from __future__ import annotations

from sqlmodel import Session

from carcatcher.db.models import Listing


def _seed(engine, **overrides):
    defaults = dict(
        source="vw", source_id="1", url="https://x/1", model="id4", trim="Pro",
        price_eur=30000, mileage_km=10000, year=2024, power_kw=150,
        condition="used", location="Berlin", title="VW ID.4 Pro",
    )
    defaults.update(overrides)
    with Session(engine) as session:
        session.add(Listing(**defaults))
        session.commit()


def test_returns_active_listings(client, test_engine):
    _seed(test_engine, source_id="1")
    resp = client.get("/api/listings")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["source_id"] == "1"


def test_filters_by_model(client, test_engine):
    _seed(test_engine, source_id="1", model="id3")
    _seed(test_engine, source_id="2", model="id4")
    resp = client.get("/api/listings", params={"model": "id4"})
    assert [i["source_id"] for i in resp.json()] == ["2"]


def test_filters_by_source(client, test_engine):
    _seed(test_engine, source_id="1", source="vw")
    _seed(test_engine, source_id="2", source="autoscout24")
    resp = client.get("/api/listings", params={"source": "autoscout24"})
    assert [i["source_id"] for i in resp.json()] == ["2"]


def test_filters_by_max_price(client, test_engine):
    _seed(test_engine, source_id="1", price_eur=20000)
    _seed(test_engine, source_id="2", price_eur=40000)
    resp = client.get("/api/listings", params={"max_price": 30000})
    assert [i["source_id"] for i in resp.json()] == ["1"]


def test_filters_by_max_km(client, test_engine):
    _seed(test_engine, source_id="1", mileage_km=5000)
    _seed(test_engine, source_id="2", mileage_km=50000)
    resp = client.get("/api/listings", params={"max_km": 10000})
    assert [i["source_id"] for i in resp.json()] == ["1"]


def test_filters_by_trim_substring_case_insensitive(client, test_engine):
    _seed(test_engine, source_id="1", trim="Pro Performance")
    _seed(test_engine, source_id="2", trim="Pure")
    resp = client.get("/api/listings", params={"trim": "pro"})
    assert [i["source_id"] for i in resp.json()] == ["1"]


def test_excludes_gone_listings_by_default(client, test_engine):
    _seed(test_engine, source_id="1", status="gone")
    resp = client.get("/api/listings")
    assert resp.json() == []


def test_sorted_by_price_ascending_with_nulls_last(client, test_engine):
    _seed(test_engine, source_id="1", price_eur=40000)
    _seed(test_engine, source_id="2", price_eur=20000)
    _seed(test_engine, source_id="3", price_eur=None)
    resp = client.get("/api/listings")
    assert [i["source_id"] for i in resp.json()] == ["2", "1", "3"]
```

- [ ] **Step 2: Write the failing test `backend/tests/test_api_refresh.py`**

```python
"""Tests for POST /api/refresh."""

from __future__ import annotations

from carcatcher.app_state import AppState, set_state
from carcatcher.scraping.base import RawListing


class _FakeParser:
    def __init__(self, name, listings):
        self.name = name
        self._listings = listings

    def fetch_listings(self, model):
        return [l for l in self._listings if l.model == model]


def _raw(source_id):
    return RawListing(
        source="vw", source_id=source_id, url=f"https://x/{source_id}", model="id4",
        trim="Pro", price_eur=30000, mileage_km=1000, year=2024, power_kw=150,
        condition="used", location="Berlin", title="VW ID.4 Pro",
    )


def test_refresh_returns_summary(client, test_engine):
    set_state(AppState(parsers={"vw": _FakeParser("vw", [_raw("1")])}))
    resp = client.post("/api/refresh")
    assert resp.status_code == 200
    body = resp.json()
    assert body["added"] == 1
    assert body["updated"] == 0
    assert body["gone"] == 0
    assert body["failed_sources"] == []
    assert "refreshed_at" in body


def test_refresh_then_listings_reflects_new_rows(client, test_engine):
    set_state(AppState(parsers={"vw": _FakeParser("vw", [_raw("1")])}))
    client.post("/api/refresh")
    resp = client.get("/api/listings")
    assert len(resp.json()) == 1
```

- [ ] **Step 3: Run both to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_api_listings.py tests/test_api_refresh.py -v`
Expected: FAIL — current routes reference deleted fields (`battery_kwh`, `deal_score`, etc.) and `test_api_refresh.py` no longer matches the cron-secret-gated `202`-response API.

- [ ] **Step 4: Replace `backend/carcatcher/config.py` entirely**

```python
"""Application configuration, loaded from environment / .env via pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. All values are overridable via environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "CarCatcher"
    # SQLite file path. In production this lives on the NFS bind-mount.
    database_path: str = "./data/carcatcher.db"

    @property
    def database_url(self) -> str:
        """SQLAlchemy URL for the SQLite database."""
        return f"sqlite:///{self.database_path}"


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the process-wide Settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
```

- [ ] **Step 5: Replace `backend/carcatcher/app_state.py` entirely**

```python
"""Process-wide singleton: the parser registry. Built in the FastAPI lifespan;
overridable in tests via `set_state`."""

from __future__ import annotations

from dataclasses import dataclass

from carcatcher.scraping.base import Parser
from carcatcher.scraping.registry import build_registry


@dataclass
class AppState:
    parsers: dict[str, Parser]


_state: AppState | None = None


def build_state() -> AppState:
    return AppState(parsers=build_registry())


def set_state(state: AppState | None) -> None:
    global _state
    _state = state


def get_state() -> AppState:
    if _state is None:
        raise RuntimeError("AppState not initialized")
    return _state
```

- [ ] **Step 6: Replace `backend/carcatcher/api/routes/listings.py` entirely**

```python
"""Listing query endpoint: filtered list of active (or all) listings."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import asc
from sqlmodel import Session, func, select

from carcatcher.db.engine import get_session
from carcatcher.db.models import Listing, ListingStatus

router = APIRouter()


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
    condition: str
    location: str | None
    title: str
    status: str
    first_seen_at: datetime
    last_seen_at: datetime


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
    return [ListingRead.model_validate(i) for i in items]
```

- [ ] **Step 7: Replace `backend/carcatcher/api/routes/refresh.py` entirely**

```python
"""Manual crawl trigger — synchronous (2 sources x 2 models, no AI calls, fast
enough to complete within one request)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlmodel import Session

from carcatcher.app_state import get_state
from carcatcher.crawl import run_crawl
from carcatcher.db.engine import get_engine

router = APIRouter()


class RefreshSummary(BaseModel):
    added: int
    updated: int
    gone: int
    failed_sources: list[str]
    refreshed_at: datetime


@router.post("/refresh", response_model=RefreshSummary)
def refresh() -> RefreshSummary:
    parsers = get_state().parsers
    with Session(get_engine()) as session:
        summary = run_crawl(session, parsers)
    return RefreshSummary(
        added=summary.added,
        updated=summary.updated,
        gone=summary.gone,
        failed_sources=summary.failed_sources,
        refreshed_at=summary.refreshed_at,
    )
```

- [ ] **Step 8: Replace `backend/carcatcher/main.py` entirely**

```python
"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from carcatcher.api.routes import health, listings, refresh
from carcatcher.app_state import build_state, set_state
from carcatcher.config import get_settings
from carcatcher.db.engine import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    set_state(build_state())
    try:
        yield
    finally:
        set_state(None)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)
    app.include_router(health.router, prefix="/api")
    app.include_router(listings.router, prefix="/api")
    app.include_router(refresh.router, prefix="/api")
    return app


app = create_app()
```

- [ ] **Step 9: Delete `schemas.py` and the dead route files**

```bash
cd /root/repos/carcatcher
git rm backend/carcatcher/schemas.py \
       backend/carcatcher/api/routes/recommend.py \
       backend/carcatcher/api/routes/saved_searches.py \
       backend/carcatcher/api/routes/search.py \
       backend/carcatcher/api/routes/settings.py \
       backend/carcatcher/api/routes/models.py
```

- [ ] **Step 10: Run the full test file set for this task to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_api_listings.py tests/test_api_refresh.py tests/test_api_health.py -v`
Expected: all PASS (health test needed no changes — confirm it's unaffected).

- [ ] **Step 11: Commit**

```bash
cd /root/repos/carcatcher
git add backend/carcatcher/config.py backend/carcatcher/app_state.py backend/carcatcher/main.py \
        backend/carcatcher/api/routes/listings.py backend/carcatcher/api/routes/refresh.py \
        backend/tests/test_api_listings.py backend/tests/test_api_refresh.py
git commit -m "feat: rewrite API to 2 endpoints (listings, refresh); drop AI/saved-search/NL-search routes"
```

---

## Task 7: Delete dead backend packages, trim dependencies, clean up test support

**Files:**
- Delete: `backend/carcatcher/ai/`, `backend/carcatcher/scoring/`, `backend/carcatcher/normalization/`, `backend/carcatcher/research/`, `backend/carcatcher/scheduler/`, `backend/carcatcher/pipeline/`, `backend/carcatcher/settings_store.py`, `backend/model_guides/`
- Delete: `backend/carcatcher/queries.py` (added by Amendment 2 below — a gap in the original plan)
- Delete: all now-orphaned test files (list in Step 2), including `backend/tests/test_snapshot.py` (added by Amendment 2 below)
- Modify: `backend/carcatcher/scraping/base.py` — remove the deprecated backwards-compat shim (see Step 2a)
- Modify: `backend/carcatcher/scraping/autoscout24.py` — remove the deprecated `AutoScout24Scraper` alias (see Step 2a)
- Modify: `backend/tests/conftest.py`
- Delete: `backend/tests/fakes.py`
- Modify: `backend/pyproject.toml`

**Interfaces:** none new — this task only removes dead code and confirms nothing still imports it.

**Amendment 1 (added after Task 3's implementer hit a blocker; see Task 3's Amendment 2):** Task 1 left a temporary `# DEPRECATED` shim in `base.py`/`autoscout24.py` (`ListingStub`, `RawPage`, `Scraper`, `sha256_text`, and an `AutoScout24Scraper` alias) because `kleinanzeigen.py`/`mobilede.py` needed it. Those were deleted in Task 3, but a repo-wide grep found the shim's *actual* last consumers are `carcatcher/pipeline/run.py` and `backend/tests/test_multisource.py` — both deleted in this task's Step 2. **This task is therefore where the shim finally gets removed.** Step 2a below does that; do it right after Step 2's deletions, before touching `conftest.py`.

**Amendment 2 (added after Task 7's implementer's Step 1 grep surfaced two more gaps):** Two files were never scheduled for deletion anywhere in the original plan, and are now confirmed dead: `backend/carcatcher/queries.py` (imports `carcatcher.normalization.makes` and `carcatcher.schemas`, both deleted; its only importers are `carcatcher/scoring/candidates.py` — deleted in this task's Step 2 — and `test_battery_search.py`/`test_nl_recommend.py`, both already in Step 2's deletion list) and `backend/tests/test_snapshot.py` (imports `CrawlRun`/`ListingSearch`/`RunStatus`/`SavedSearch`/`Shortlist`/`ShortlistItem` from `db.models`, all removed by Task 4; it tested `pipeline/snapshot.py`'s mark-gone/prune logic, superseded by `crawl.py`'s `_mark_gone` in Task 5). Both are added to Step 2's deletion command below.

- [ ] **Step 1: Grep for any remaining references to the packages about to be deleted**

Run: `cd backend && grep -rln --include='*.py' -E 'carcatcher\.(ai|scoring|normalization|research|scheduler|pipeline|settings_store)' carcatcher tests`
Expected: only files this task is about to delete/already know about should appear (e.g. `tests/fakes.py` for `FakeAnthropic`). If a file NOT already scheduled for deletion shows up, stop and read it — it means Task 6 missed an import that needs fixing first.

- [ ] **Step 2: Delete the dead packages, model guides, and their tests**

```bash
cd /root/repos/carcatcher
git rm -r backend/carcatcher/ai backend/carcatcher/scoring backend/carcatcher/normalization \
          backend/carcatcher/research backend/carcatcher/scheduler backend/carcatcher/pipeline \
          backend/model_guides
git rm backend/carcatcher/settings_store.py
git rm backend/carcatcher/queries.py
git rm backend/tests/fakes.py
git rm backend/tests/test_ai_client.py backend/tests/test_evaluate.py backend/tests/test_extractor.py \
       backend/tests/test_guide_categorizer.py backend/tests/test_guide_generator.py \
       backend/tests/test_model_categorizer.py backend/tests/test_model_reassign.py \
       backend/tests/test_models_api.py backend/tests/test_multisource.py \
       backend/tests/test_nl_recommend.py backend/tests/test_normalize.py \
       backend/tests/test_ollama_client.py backend/tests/test_pipeline.py \
       backend/tests/test_run_pipeline.py backend/tests/test_saved_searches.py \
       backend/tests/test_scheduler.py backend/tests/test_score.py \
       backend/tests/test_search_match.py backend/tests/test_search_scoped.py \
       backend/tests/test_settings_api.py backend/tests/test_baseline.py \
       backend/tests/test_battery.py backend/tests/test_battery_search.py \
       backend/tests/test_favorites.py backend/tests/test_snapshot.py
```

If any `git rm` above errors with "pathspec did not match" (file already gone or never existed under that exact name), run `git status` to see the real filename and adjust — do not silently skip verifying the corresponding source module is actually deleted.

- [ ] **Step 2a: Remove the now-unused deprecated shim from `base.py` and `autoscout24.py`**

With `pipeline/run.py` and `test_multisource.py` deleted, nothing imports `ListingStub`, `RawPage`, `Scraper`, `sha256_text`, or `AutoScout24Scraper` anymore. Delete all of it. `backend/carcatcher/scraping/base.py` should end up containing exactly the `Model`/`RawListing`/`Parser` block from Task 1's Step 1 (the `# BACKWARDS COMPATIBILITY` banner and everything under it removed). In `backend/carcatcher/scraping/autoscout24.py`, delete the `AutoScout24Scraper = AutoScout24Parser` alias line (and its clarifying comment) at the bottom of the file.

Run: `cd backend && grep -rn "ListingStub\|RawPage\|Scraper\b\|sha256_text\|AutoScout24Scraper" carcatcher tests`
Expected: no matches. If something still matches, stop — it means another consumer exists that this task's Step 2 didn't account for; read it before deleting anything further.

- [ ] **Step 3: Replace `backend/tests/conftest.py` entirely**

```python
"""Shared pytest fixtures: isolated DB + TestClient."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

from carcatcher.db import engine as db_engine
from carcatcher.main import create_app


@pytest.fixture()
def test_engine():
    """A fresh in-memory SQLite engine shared across connections for one test."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    db_engine.set_engine(engine)
    yield engine
    db_engine.set_engine(None)  # type: ignore[arg-type]


@pytest.fixture()
def client(test_engine):
    app = create_app()
    with TestClient(app) as c:
        yield c
```

- [ ] **Step 4: Trim `backend/pyproject.toml` dependencies**

Remove `anthropic>=0.40.0`, `apscheduler>=3.10.4`, `numpy>=2.1.0` from `dependencies`. Resulting `dependencies` block:

```toml
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "sqlmodel>=0.0.22",
    "pydantic>=2.9.0",
    "pydantic-settings>=2.6.0",
    "httpx>=0.27.0",
    "beautifulsoup4>=4.12.0",
]
```

Keep `[dependency-groups] dev` (pytest, pytest-asyncio, pytest-cov, respx) unchanged — `respx` is now actively used by Tasks 1 and 2's tests.

- [ ] **Step 5: Re-sync the environment and run the full backend suite**

Run: `cd backend && uv sync && .venv/bin/pytest -v 2>&1 | tail -60`
Expected: every remaining test file passes. If any test still imports a deleted module, delete that test file too (it was missed in Step 2) and re-run.

- [ ] **Step 6: Commit**

```bash
cd /root/repos/carcatcher
git add -A backend/
git commit -m "chore: delete AI/scoring/normalization/scheduler/pipeline/model-guides packages and their tests"
```

---

## Task 8: Backend verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend test suite with coverage**

Run: `cd backend && .venv/bin/pytest --cov=carcatcher -v 2>&1 | tail -80`
Expected: all tests PASS; no import errors; no skipped tests due to missing modules.

- [ ] **Step 2: Confirm no dead imports remain anywhere in the backend package**

Run: `cd backend && .venv/bin/python -c "import carcatcher.main; carcatcher.main.create_app()"`
Expected: exits cleanly with no traceback (this exercises every route/module import path at once, catching anything the test suite's mocking might have papered over).

- [ ] **Step 3: Confirm the trimmed dependency set installs cleanly from scratch**

Run: `cd backend && rm -rf .venv && uv sync && .venv/bin/pytest -q`
Expected: clean install, all tests pass.

No commit for this task — it's a checkpoint, not a change. If anything fails, fix it and fold the fix into the relevant earlier task's commit history isn't necessary (just commit the fix directly here with a `fix:` message).

---

## Task 9: Frontend types + API client

**Files:**
- Create: `frontend/src/types/index.ts` (replaces existing content entirely)
- Create: `frontend/src/api/client.ts` (replaces existing content entirely)
- Modify: `frontend/src/hooks/useListings.ts`
- Modify: `frontend/src/lib/format.ts`

**Interfaces:**
- Produces: `Listing`, `ListingQuery`, `RefreshSummary` types; `getHealth()`, `getListings(query)`, `refresh()` API functions. Used by Tasks 10-12.

- [ ] **Step 1: Replace `frontend/src/types/index.ts` entirely**

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
  condition: string;
  location: string | null;
  title: string;
  status: string;
  first_seen_at: string;
  last_seen_at: string;
}

export interface ListingQuery {
  model?: string;
  source?: string;
  max_price?: number;
  max_km?: number;
  trim?: string;
}

export interface RefreshSummary {
  added: number;
  updated: number;
  gone: number;
  failed_sources: string[];
  refreshed_at: string;
}
```

- [ ] **Step 2: Replace `frontend/src/api/client.ts` entirely**

```typescript
/** Thin fetch wrapper around the CarCatcher API. */

import type { Listing, ListingQuery, RefreshSummary } from "../types";

const BASE = "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`);
  if (!resp.ok) {
    throw new ApiError(resp.status, `GET ${path} failed: ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export interface HealthResponse {
  status: string;
}

export function getHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>("/health");
}

export function getListings(query: ListingQuery = {}): Promise<Listing[]> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const qs = params.toString();
  return apiGet<Listing[]>(`/listings${qs ? `?${qs}` : ""}`);
}

export async function refresh(): Promise<RefreshSummary> {
  const resp = await fetch(`${BASE}/refresh`, { method: "POST" });
  if (!resp.ok) {
    throw new ApiError(resp.status, `refresh failed: ${resp.status}`);
  }
  return (await resp.json()) as RefreshSummary;
}
```

- [ ] **Step 3: Update `frontend/src/hooks/useListings.ts` to match the un-paginated `Listing[]` response**

Replace the `State`/import types (the hook body's logic is unchanged):

```typescript
import { useCallback, useEffect, useState } from "react";
import { getListings } from "../api/client";
import type { Listing, ListingQuery } from "../types";

interface State {
  data: Listing[] | null;
  loading: boolean;
  error: string | null;
}

export function useListings(query: ListingQuery) {
  const [state, setState] = useState<State>({
    data: null,
    loading: true,
    error: null,
  });

  const key = JSON.stringify(query);

  const reload = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }));
    getListings(query)
      .then((data) => setState({ data, loading: false, error: null }))
      .catch((e: unknown) =>
        setState({
          data: null,
          loading: false,
          error: e instanceof Error ? e.message : "Failed to load listings",
        }),
      );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { ...state, reload };
}
```

- [ ] **Step 4: Replace `frontend/src/lib/format.ts` entirely** (drop the unused `raw` fallback param and `formatKmPerYear`, which no field in the simplified `Listing` needs)

```typescript
const EUR = new Intl.NumberFormat("de-DE", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});
const NUM = new Intl.NumberFormat("de-DE");

export function formatPrice(value: number | null): string {
  return value != null ? EUR.format(value) : "—";
}

export function formatKm(value: number | null): string {
  return value != null ? `${NUM.format(value)} km` : "—";
}

export function formatYear(value: number | null): string {
  return value != null ? String(value) : "—";
}
```

- [ ] **Step 5: Type-check**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -60`
Expected: errors will appear for `ListingsTable.tsx`, `RefreshControls.tsx`, `Dashboard.tsx`, `App.tsx` (still referencing old types/fields) — that's expected until Tasks 10-12. Confirm there are **no** errors inside `types/index.ts`, `api/client.ts`, `hooks/useListings.ts`, or `lib/format.ts` themselves.

- [ ] **Step 6: Commit**

```bash
cd /root/repos/carcatcher
git add frontend/src/types/index.ts frontend/src/api/client.ts frontend/src/hooks/useListings.ts frontend/src/lib/format.ts
git commit -m "feat: trim frontend types/API client to the simplified Listing shape"
```

---

## Task 10: ListingsTable component

**Files:**
- Create: `frontend/src/components/ListingsTable.tsx` (replaces existing content entirely)
- Create: `frontend/src/components/ListingsTable.test.tsx` (replaces existing content entirely)

**Interfaces:**
- Consumes: `Listing` (Task 9), `formatKm`/`formatPrice`/`formatYear` (Task 9).
- Produces: `ListingsTable` component, `TableFilters` interface (`model?`, `source?`, `max_price?`, `max_km?`, `trim?`), `SOURCE_LABEL`. Used by Task 12's `Dashboard.tsx`.

- [ ] **Step 1: Write the failing test `frontend/src/components/ListingsTable.test.tsx`**

```typescript
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ListingsTable } from "./ListingsTable";
import type { Listing } from "../types";

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
  condition: "used",
  location: "Berlin",
  title: "VW ID.4 Pro",
  status: "active",
  first_seen_at: "2026-08-11T00:00:00Z",
  last_seen_at: "2026-08-11T00:00:00Z",
};

describe("ListingsTable", () => {
  it("renders a row per listing", () => {
    render(<ListingsTable items={[listing]} filters={{}} onFilterChange={() => {}} />);
    expect(screen.getByText("Pro Performance")).toBeInTheDocument();
    expect(screen.getByText("ID.4")).toBeInTheDocument();
    expect(screen.getByText("34.410 €")).toBeInTheDocument();
  });

  it("shows the empty state when there are no listings", () => {
    render(<ListingsTable items={[]} filters={{}} onFilterChange={() => {}} />);
    expect(screen.getByText("No listings match these filters.")).toBeInTheDocument();
  });

  it("calls onFilterChange when the trim filter changes", () => {
    const onFilterChange = vi.fn();
    render(<ListingsTable items={[]} filters={{}} onFilterChange={onFilterChange} />);
    fireEvent.change(screen.getByLabelText("Filter trim"), { target: { value: "Pro" } });
    expect(onFilterChange).toHaveBeenCalledWith({ trim: "Pro" });
  });

  it("calls onFilterChange when the max price filter changes", () => {
    const onFilterChange = vi.fn();
    render(<ListingsTable items={[]} filters={{}} onFilterChange={onFilterChange} />);
    fireEvent.change(screen.getByLabelText("Max price"), { target: { value: "30000" } });
    expect(onFilterChange).toHaveBeenCalledWith({ max_price: 30000 });
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/components/ListingsTable.test.tsx`
Expected: FAIL — old component has a completely different props shape (`onSelect`, `favoriteIds`, etc.) and no `Filter trim`/`Max price` labeled inputs matching this test.

- [ ] **Step 3: Replace `frontend/src/components/ListingsTable.tsx` entirely**

```typescript
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

export interface TableFilters {
  model?: string;
  source?: string;
  max_price?: number;
  max_km?: number;
  trim?: string;
}

const num = (v: string): number | undefined => (v.trim() === "" ? undefined : Number(v));

interface ListingsTableProps {
  items: Listing[];
  filters: TableFilters;
  onFilterChange: (next: TableFilters) => void;
}

export function ListingsTable({ items, filters, onFilterChange }: ListingsTableProps) {
  const f = filters;
  const set = (patch: Partial<TableFilters>) => onFilterChange({ ...f, ...patch });

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-3 font-medium">Model</th>
            <th className="px-4 py-3 font-medium">Trim</th>
            <th className="px-4 py-3 font-medium">Price</th>
            <th className="px-4 py-3 font-medium">KM</th>
            <th className="px-4 py-3 font-medium">Year</th>
            <th className="px-4 py-3 font-medium">Power</th>
            <th className="px-4 py-3 font-medium">Condition</th>
            <th className="px-4 py-3 font-medium">Location</th>
            <th className="px-4 py-3 font-medium">Source</th>
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
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.length === 0 ? (
            <tr>
              <td colSpan={10} className="px-4 py-12 text-center text-slate-500">
                No listings match these filters.
              </td>
            </tr>
          ) : (
            items.map((l) => (
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
                  {l.condition === "new" ? "Neu" : "Gebraucht"}
                </td>
                <td className="max-w-[12rem] px-4 py-3 text-slate-600">
                  <span className="line-clamp-1">{l.location ?? "—"}</span>
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-500">
                  {SOURCE_LABEL[l.source] ?? l.source}
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npx vitest run src/components/ListingsTable.test.tsx`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /root/repos/carcatcher
git add frontend/src/components/ListingsTable.tsx frontend/src/components/ListingsTable.test.tsx
git commit -m "feat: rewrite ListingsTable for the simplified Listing shape and filter set"
```

---

## Task 11: RefreshControls component

**Files:**
- Create: `frontend/src/components/RefreshControls.tsx` (replaces existing content entirely)
- Create: `frontend/src/components/RefreshControls.test.tsx` (replaces existing content entirely)
- Delete: `frontend/src/components/RunStatusPill.tsx`, `frontend/src/components/RunStatusPill.test.tsx`
- Delete: `frontend/src/lib/secret.ts` (and its test, if one exists)

**Interfaces:**
- Consumes: `refresh()` (Task 9).
- Produces: `RefreshControls` component with `{ onComplete?: () => void }` props. Used by Task 12's `Dashboard.tsx`.

- [ ] **Step 1: Check whether `frontend/src/lib/secret.ts` has a test file and whether anything besides the old `RefreshControls` imports it**

Run: `cd frontend && grep -rl "lib/secret" src`
Expected: only `RefreshControls.tsx` (about to be rewritten) and possibly its own test file. If `SavedSearches.tsx` (deleted in Task 12) also references it, that's fine — it's being deleted too.

- [ ] **Step 2: Write the failing test `frontend/src/components/RefreshControls.test.tsx`**

```typescript
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { RefreshControls } from "./RefreshControls";
import * as client from "../api/client";

describe("RefreshControls", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("shows a loading state while refreshing, then the summary", async () => {
    vi.spyOn(client, "refresh").mockResolvedValue({
      added: 2,
      updated: 1,
      gone: 0,
      failed_sources: [],
      refreshed_at: "2026-08-11T12:00:00Z",
    });
    const onComplete = vi.fn();
    render(<RefreshControls onComplete={onComplete} />);

    fireEvent.click(screen.getByRole("button", { name: "Update search" }));
    expect(screen.getByRole("button")).toHaveTextContent("Updating…");

    await waitFor(() => expect(onComplete).toHaveBeenCalled());
    expect(screen.getByText(/2 new/)).toBeInTheDocument();
  });

  it("shows an error message when refresh fails", async () => {
    vi.spyOn(client, "refresh").mockRejectedValue(new Error("network down"));
    render(<RefreshControls />);
    fireEvent.click(screen.getByRole("button", { name: "Update search" }));
    await waitFor(() => expect(screen.getByText("network down")).toBeInTheDocument());
  });

  it("shows which sources failed when a refresh partially fails", async () => {
    vi.spyOn(client, "refresh").mockResolvedValue({
      added: 1,
      updated: 0,
      gone: 0,
      failed_sources: ["vw"],
      refreshed_at: "2026-08-11T12:00:00Z",
    });
    render(<RefreshControls />);
    fireEvent.click(screen.getByRole("button", { name: "Update search" }));
    await waitFor(() => expect(screen.getByText(/vw/)).toBeInTheDocument());
  });
});
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd frontend && npx vitest run src/components/RefreshControls.test.tsx`
Expected: FAIL — old component requires `ensureSecret()`/polling and has no `RefreshSummary`-shaped text output.

- [ ] **Step 4: Replace `frontend/src/components/RefreshControls.tsx` entirely**

```typescript
import { useState } from "react";
import { refresh } from "../api/client";
import type { RefreshSummary } from "../types";

export function RefreshControls({ onComplete }: { onComplete?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState<RefreshSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const onClick = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await refresh();
      setSummary(result);
      onComplete?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Refresh failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-3">
      {summary && (
        <span className="text-xs text-slate-500">
          Updated {new Date(summary.refreshed_at).toLocaleTimeString("de-DE")} — +{summary.added}{" "}
          new, {summary.updated} updated, {summary.gone} gone
          {summary.failed_sources.length > 0 && (
            <span className="text-rose-600"> ({summary.failed_sources.join(", ")} failed)</span>
          )}
        </span>
      )}
      <button
        onClick={onClick}
        disabled={busy}
        className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        {busy ? "Updating…" : "Update search"}
      </button>
      {error && <span className="text-xs text-rose-600">{error}</span>}
    </div>
  );
}
```

- [ ] **Step 5: Delete `RunStatusPill` and `lib/secret.ts`**

```bash
cd /root/repos/carcatcher
git rm frontend/src/components/RunStatusPill.tsx frontend/src/components/RunStatusPill.test.tsx
git rm frontend/src/lib/secret.ts
```

(If `lib/secret.ts` has no test file, the second command will only remove the one file — that's fine.)

- [ ] **Step 6: Run to verify the new test passes**

Run: `cd frontend && npx vitest run src/components/RefreshControls.test.tsx`
Expected: all 3 tests PASS.

- [ ] **Step 7: Commit**

```bash
cd /root/repos/carcatcher
git add -A frontend/src/components/RefreshControls.tsx frontend/src/components/RefreshControls.test.tsx
git commit -m "feat: rewrite RefreshControls for synchronous refresh; drop cron-secret prompt and run polling"
```

---

## Task 12: Dashboard + App, delete dead pages/components, trim package.json

**Files:**
- Create: `frontend/src/pages/Dashboard.tsx` (replaces existing content entirely)
- Create: `frontend/src/pages/Dashboard.test.tsx` (replaces existing content entirely)
- Create: `frontend/src/App.tsx` (replaces existing content entirely)
- Create: `frontend/src/App.test.tsx` (replaces existing content entirely)
- Delete: `frontend/src/pages/ModelGuides.tsx`, `ModelGuides.test.tsx`, `SavedSearches.tsx`, `SavedSearches.test.tsx`
- Delete: `frontend/src/components/ListingDetailDrawer.tsx`, `.test.tsx`, `RecommendationPanel.tsx`, `.test.tsx`, `DealScoreBadge.tsx`, `.test.tsx`, `AiToggle.tsx`, `.test.tsx`, `SearchBar.tsx`, `.test.tsx`
- Modify: `frontend/package.json`

**Interfaces:**
- Consumes: `ListingsTable`/`TableFilters` (Task 10), `RefreshControls` (Task 11), `useListings`/`useDebounce`/`getHealth` (Task 9).
- Produces: `Dashboard`, default-exported `App`.

- [ ] **Step 1: Confirm `react-markdown`/`recharts`/`remark-gfm` are only used by the components about to be deleted**

Run: `cd frontend && grep -rl -E "react-markdown|recharts|remark-gfm" src`
Expected: only `ModelGuides.tsx` (react-markdown, remark-gfm) and `RecommendationPanel.tsx` or similar (recharts) — both about to be deleted in this task. If any file NOT being deleted shows up, keep that dependency in `package.json` and note it in the commit message instead of removing it.

- [ ] **Step 2: Write the failing test `frontend/src/pages/Dashboard.test.tsx`**

```typescript
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { Dashboard } from "./Dashboard";
import * as client from "../api/client";
import type { Listing } from "../types";

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
  condition: "used",
  location: "Berlin",
  title: "VW ID.4 Pro",
  status: "active",
  first_seen_at: "2026-08-11T00:00:00Z",
  last_seen_at: "2026-08-11T00:00:00Z",
};

describe("Dashboard", () => {
  it("loads and displays listings from the API", async () => {
    vi.spyOn(client, "getListings").mockResolvedValue([listing]);
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByText("1 found")).toBeInTheDocument());
    expect(screen.getByText("Pro")).toBeInTheDocument();
  });

  it("shows an error message when listings fail to load", async () => {
    vi.spyOn(client, "getListings").mockRejectedValue(new Error("boom"));
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByText("boom")).toBeInTheDocument());
  });
});
```

- [ ] **Step 3: Write the failing test `frontend/src/App.test.tsx`**

```typescript
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import App from "./App";
import * as client from "./api/client";

describe("App", () => {
  it("shows API healthy once the health check resolves", async () => {
    vi.spyOn(client, "getHealth").mockResolvedValue({ status: "ok" });
    vi.spyOn(client, "getListings").mockResolvedValue([]);
    render(<App />);
    await waitFor(() => expect(screen.getByText("API healthy")).toBeInTheDocument());
  });

  it("shows API down when the health check fails", async () => {
    vi.spyOn(client, "getHealth").mockRejectedValue(new Error("down"));
    vi.spyOn(client, "getListings").mockResolvedValue([]);
    render(<App />);
    await waitFor(() => expect(screen.getByText("API down")).toBeInTheDocument());
  });
});
```

- [ ] **Step 4: Run both to verify they fail**

Run: `cd frontend && npx vitest run src/pages/Dashboard.test.tsx src/App.test.tsx`
Expected: FAIL — old `Dashboard`/`App` have entirely different shapes (nav tabs, facets, AI toggle, etc.).

- [ ] **Step 5: Replace `frontend/src/pages/Dashboard.tsx` entirely**

```typescript
import { useState } from "react";
import { useDebounce } from "../hooks/useDebounce";
import { useListings } from "../hooks/useListings";
import { ListingsTable, type TableFilters } from "../components/ListingsTable";
import { RefreshControls } from "../components/RefreshControls";
import type { ListingQuery } from "../types";

function toQuery(f: TableFilters): ListingQuery {
  return {
    model: f.model || undefined,
    source: f.source || undefined,
    trim: f.trim || undefined,
    max_price: f.max_price,
    max_km: f.max_km,
  };
}

export function Dashboard() {
  const [filters, setFilters] = useState<TableFilters>({});
  const debouncedFilters = useDebounce(filters, 300);
  const query: ListingQuery = toQuery(debouncedFilters);
  const { data, loading, error, reload } = useListings(query);

  const items = data ?? [];
  const hasFilters = Object.values(filters).some((v) => v !== undefined && v !== "");

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-3 text-lg font-semibold text-slate-800">
          VW ID.3 / ID.4 offers
          <span className="text-sm font-normal text-slate-400">{items.length} found</span>
        </h2>
        <div className="flex flex-wrap items-center justify-end gap-x-4 gap-y-2">
          {hasFilters && (
            <button
              type="button"
              onClick={() => setFilters({})}
              className="text-sm font-medium text-slate-500 hover:text-slate-700"
            >
              Clear filters
            </button>
          )}
          <RefreshControls onComplete={reload} />
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {error}
        </div>
      )}
      {loading && !data && <div className="text-slate-400">Loading…</div>}

      <ListingsTable items={items} filters={filters} onFilterChange={setFilters} />
    </section>
  );
}
```

- [ ] **Step 6: Replace `frontend/src/App.tsx` entirely**

```typescript
import { useEffect, useState } from "react";
import { getHealth } from "./api/client";
import { Dashboard } from "./pages/Dashboard";

type HealthState = "checking" | "ok" | "down";

export default function App() {
  const [health, setHealth] = useState<HealthState>("checking");

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((r) => !cancelled && setHealth(r.status === "ok" ? "ok" : "down"))
      .catch(() => !cancelled && setHealth("down"));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-[1800px] items-center justify-between px-6 py-4">
          <h1 className="text-xl font-semibold tracking-tight">🚗 CarCatcher</h1>
          <HealthPill state={health} />
        </div>
      </header>
      <main className="mx-auto max-w-[1800px] px-6 py-8">
        <Dashboard />
      </main>
    </div>
  );
}

function HealthPill({ state }: { state: HealthState }) {
  const styles: Record<HealthState, string> = {
    checking: "bg-slate-100 text-slate-500",
    ok: "bg-emerald-100 text-emerald-700",
    down: "bg-rose-100 text-rose-700",
  };
  const label: Record<HealthState, string> = {
    checking: "checking…",
    ok: "API healthy",
    down: "API down",
  };
  return (
    <span className={`rounded-full px-3 py-1 text-xs font-medium ${styles[state]}`}>
      {label[state]}
    </span>
  );
}
```

- [ ] **Step 7: Delete dead pages and components**

```bash
cd /root/repos/carcatcher
git rm frontend/src/pages/ModelGuides.tsx frontend/src/pages/ModelGuides.test.tsx \
       frontend/src/pages/SavedSearches.tsx frontend/src/pages/SavedSearches.test.tsx \
       frontend/src/components/ListingDetailDrawer.tsx frontend/src/components/ListingDetailDrawer.test.tsx \
       frontend/src/components/RecommendationPanel.tsx frontend/src/components/RecommendationPanel.test.tsx \
       frontend/src/components/DealScoreBadge.tsx frontend/src/components/DealScoreBadge.test.tsx \
       frontend/src/components/AiToggle.tsx frontend/src/components/AiToggle.test.tsx \
       frontend/src/components/SearchBar.tsx frontend/src/components/SearchBar.test.tsx
```

- [ ] **Step 8: Trim `frontend/package.json`** — remove `react-markdown`, `recharts`, `remark-gfm` from `dependencies` (confirmed orphaned in Step 1), keep everything else unchanged.

- [ ] **Step 9: Reinstall and run type-check + full frontend test suite**

Run: `cd frontend && npm install && npx tsc --noEmit && npx vitest run`
Expected: `tsc` reports zero errors; every remaining test file passes, including the new `Dashboard.test.tsx` and `App.test.tsx`.

- [ ] **Step 10: Commit**

```bash
cd /root/repos/carcatcher
git add -A frontend/
git commit -m "feat: rewrite Dashboard/App as single-view; delete AI/saved-search/model-guide UI"
```

---

## Task 13: Frontend verification

**Files:** none (verification only)

- [ ] **Step 1: Full type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: zero errors.

- [ ] **Step 2: Full test suite**

Run: `cd frontend && npx vitest run`
Expected: all test files pass, zero skipped.

- [ ] **Step 3: Production build**

Run: `cd frontend && npm run build`
Expected: clean build, no errors, output written to `dist/`.

No commit for this task unless a fix is needed — if so, commit it here with a `fix:` message.

---

## Task 14: Infra — docker-compose.yml + .env.example

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`

**Interfaces:** none.

- [ ] **Step 1: Remove the Firecrawl service block from `docker-compose.yml`**

Delete the entire `# --- Firecrawl (self-hosted) ---` section: `firecrawl-redis`, `firecrawl-postgres`, `firecrawl-rabbitmq`, `firecrawl-playwright`, `firecrawl-api` services, and the trailing `volumes: firecrawl-pgdata:` block. Also remove the comment block at the top of the file referencing Firecrawl self-hosting. Resulting file:

```yaml
# CarCatcher stack: api (FastAPI) + ui (nginx/React).

services:
  api:
    build: ./backend
    restart: unless-stopped
    env_file: .env
    environment:
      - DATABASE_PATH=/data/db/carcatcher.db
    volumes:
      - ${DATA_DIR:-./data}:/data
    expose:
      - "8000"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"]
      interval: 30s
      timeout: 5s
      retries: 3

  ui:
    build: ./frontend
    restart: unless-stopped
    depends_on:
      - api
    ports:
      # Bound to the LXC; the shared nginx (LXC 111) proxies to this.
      - "${UI_PORT:-8080}:80"
```

- [ ] **Step 2: Validate the compose file parses**

Run: `docker compose -f docker-compose.yml config -q && echo OK`
Expected: `OK` (no `docker compose` binary available in this environment is also an acceptable outcome — in that case, validate with `python3 -c "import yaml; yaml.safe_load(open('docker-compose.yml'))" && echo OK` instead, just checking it's valid YAML).

- [ ] **Step 3: Replace `.env.example` entirely** (confirmed via direct read 2026-08-11 — `BASE_URL` is dropped too: `Settings` in Task 6 no longer declares it and nothing in the simplified backend reads it):

```bash
# CarCatcher configuration. Copy to .env and fill in real values (.env is gitignored).

# --- Core ---
APP_NAME=CarCatcher
# Inside the api container this is /data/db/carcatcher.db (NFS bind-mount).
DATABASE_PATH=/data/db/carcatcher.db

# Host directory bind-mounted to /data in the api container (NFS mount in prod).
DATA_DIR=/mnt/carcatcher
# Port the ui (nginx) container exposes on the LXC; shared nginx proxies here.
UI_PORT=8080
```

- [ ] **Step 4: Commit**

```bash
cd /root/repos/carcatcher
git add docker-compose.yml .env.example
git commit -m "chore: drop self-hosted Firecrawl from deploy; trim .env.example to Core vars"
```

---

## Task 15: Deploy (manual approval checkpoint)

This task changes shared/production state (merges to `main`, deploys to the live CT113 box, and — per the spec — destroys the current production SQLite database). **Do not execute this task's commands without the user explicitly confirming at execution time.** This is a checkpoint, not an automatic step.

**Files:** none (deploy only).

- [ ] **Step 1: Confirm branch is clean and all prior tasks' tests are green**

Run: `cd /root/repos/carcatcher && git status && cd backend && .venv/bin/pytest -q && cd ../frontend && npx vitest run`
Expected: clean working tree, all green.

- [ ] **Step 2: Push the branch and open a PR (or merge directly if the user prefers, per their git workflow)**

```bash
cd /root/repos/carcatcher
git push -u origin simplify-vw-id3-id4
gh pr create --title "Simplify CarCatcher to VW ID.3/ID.4 comparison table" --body "$(cat <<'EOF'
## Summary
- Replaces the full AI-assisted car-buying app with a single filterable table of VW ID.3/ID.4 listings from AutoScout24 and VW.de
- Drops AI normalization/scoring/recommendation, saved searches, shortlists, model guides, NL search, and self-hosted Firecrawl
- Manual refresh only (no scheduler); mobile.de deferred (blocked by DataDome, see spec)

## Test plan
- [x] Backend: `pytest` full suite green
- [x] Frontend: `vitest run` + `tsc --noEmit` + `npm run build` all clean
- [ ] Manual smoke test on CT113 after deploy (Step 5 below)
EOF
)"
```

Wait for the user to merge (or merge with explicit confirmation) before proceeding.

- [ ] **Step 3: Delete the existing production SQLite DB (destructive — spec-approved, confirm with user before running)**

```bash
ssh root@192.168.178.122 'ls -la /app/data/db/carcatcher.db'  # confirm it exists before deleting
ssh root@192.168.178.122 'rm /app/data/db/carcatcher.db'
```

- [ ] **Step 4: Deploy**

```bash
ssh root@192.168.178.122 'cd /app && git fetch && git reset --hard origin/main && docker compose up -d --build'
```

- [ ] **Step 5: Smoke test**

```bash
ssh root@192.168.178.122 'curl -s http://127.0.0.1:8000/api/health'
# Expected: {"status":"ok"}
curl -s -X POST https://carcatcher.jurtin.de/api/refresh
# Expected: {"added": <N>, "updated": 0, "gone": 0, "failed_sources": [], "refreshed_at": "..."}
curl -s https://carcatcher.jurtin.de/api/listings | python3 -m json.tool | head -30
# Expected: a JSON array of ID.3/ID.4 listings from vw/autoscout24
```

Also open `https://carcatcher.jurtin.de` in a browser and confirm: the table loads, "Update search" works, and filtering by max price / max km / trim narrows the results.

No git commit for this task (deploy-only). If the smoke test reveals a bug, fix it as a new commit and redeploy.
