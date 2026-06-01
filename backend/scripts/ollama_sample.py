"""Sanity-check: categorize CarCatcher listings with a local Ollama model.

Throwaway tool (NOT wired into the app). It reuses the real normalization system
prompt and field schema, then calls a local model via Ollama's OpenAI-compatible
endpoint (http://localhost:11434/v1) to eyeball extraction accuracy before we
consider swapping the Haiku call for a local provider.

Run from backend/:  uv run python scripts/ollama_sample.py
"""

from __future__ import annotations

import json

import httpx
from sqlmodel import Session, select

from carcatcher.db.engine import get_engine
from carcatcher.db.models import Listing, ListingStatus
from carcatcher.normalization.prompts import NORMALIZATION_SYSTEM
from carcatcher.normalization.schema import NORMALIZED_TOOL_SCHEMA, NormalizedListing

OLLAMA_BASE = "http://localhost:11434/v1"
MODEL = "qwen2.5:3b"

FIELDS = list(NORMALIZED_TOOL_SCHEMA["properties"].keys())

# Fallback samples — used when the dev DB has no real listings. Representative of
# real German EV/used-car classifieds (title + description).
FALLBACK_SAMPLES: list[tuple[str, str]] = [
    (
        "VW ID.4 Pro Performance 1st Max, Wärmepumpe, AHK",
        "Verkaufe meinen VW ID.4 Pro Performance (1st Max). Erstzulassung 06/2021, "
        "62.500 km. Elektro, Automatik, 150 kW (204 PS). Akkukapazität 77 kWh, "
        "SoH laut letztem Check 94%. Reichweite bis 520 km. Preis 31.900 € VB. "
        "Privatverkauf, Standort 80331 München.",
    ),
    (
        "Golf VII 2.0 TDI Highline DSG",
        "VW Golf 7 2.0 TDI Highline, EZ 03/2016, 142.000 km, Diesel, Automatik (DSG), "
        "110 kW. Scheckheftgepflegt, Händlerfahrzeug. 12.490 EUR. 50667 Köln.",
    ),
]


def _load_samples() -> list[tuple[str, str]]:
    """Prefer real active listings from the dev DB; else use the fallbacks."""
    try:
        with Session(get_engine()) as session:
            rows = session.exec(
                select(Listing)
                .where(Listing.status == ListingStatus.ACTIVE.value)
                .limit(2)
            ).all()
        real = [(r.raw_title, r.raw_text) for r in rows if r.raw_title]
        if real:
            return real
    except Exception as exc:  # no DB / not initialized -> fall back
        print(f"(no dev DB usable: {exc!r}; using fallback samples)\n")
    return FALLBACK_SAMPLES


def categorize(title: str, text: str) -> dict:
    """Call the local model via the OpenAI-compatible endpoint, return parsed JSON."""
    system = (
        NORMALIZATION_SYSTEM
        + "\n\nThere is no tool here. Respond with a SINGLE JSON object and nothing "
        + "else. Use exactly these keys (use null when not stated):\n"
        + ", ".join(FIELDS)
    )
    user = f"Title: {title}\n\nDescription: {text}"

    resp = httpx.post(
        f"{OLLAMA_BASE}/chat/completions",
        headers={"Authorization": "Bearer ollama"},  # key ignored by Ollama
        json={
            "model": MODEL,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return json.loads(content)


def main() -> None:
    samples = _load_samples()
    for i, (title, text) in enumerate(samples, 1):
        print(f"{'=' * 70}\nSAMPLE {i}\n{'=' * 70}")
        print(f"TITLE: {title}\nTEXT:  {text}\n")
        raw = categorize(title, text)
        # Validate through the real schema (coerces enums, clamps battery ranges).
        validated = NormalizedListing.model_validate(raw).model_dump()
        print("RAW MODEL JSON:")
        print(json.dumps(raw, indent=2, ensure_ascii=False))
        print("\nAFTER SCHEMA VALIDATION (what the pipeline would store):")
        print(json.dumps(validated, indent=2, ensure_ascii=False))
        print()


if __name__ == "__main__":
    main()
