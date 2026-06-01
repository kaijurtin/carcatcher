"""Seed a few sample listings and categorize them with the LOCAL Ollama model.

Brings the dashboard to life with offline-normalized data:
  init DB -> insert raw listings -> normalize via OllamaClient -> VW-ID categorize.

Run from backend/:  uv run python scripts/seed_demo.py
(Uses ai_provider=ollama; requires the local Ollama server + qwen2.5:3b.)
"""

from __future__ import annotations

import asyncio

from sqlmodel import Session, select

from carcatcher import config
from carcatcher.config import Settings
from carcatcher.app_state import build_state
from carcatcher.db.engine import get_engine, init_db
from carcatcher.db.models import Listing
from carcatcher.pipeline.categorize import categorize_active
from carcatcher.pipeline.normalize import normalize_pending
from carcatcher.scraping.base import sha256_text

SAMPLES: list[tuple[str, str, str]] = [
    (
        "kleinanzeigen", "VW ID.4 Pro Performance 1st Max, Wärmepumpe",
        "Verkaufe VW ID.4 Pro Performance (1st Max). Erstzulassung 06/2021, 62.500 km. "
        "Elektro, Automatik, 150 kW (204 PS). Akkukapazität 77 kWh, SoH 94%. "
        "Reichweite bis 520 km. 31.900 € VB. Privat, 80331 München.",
    ),
    (
        "mobilede", "VW ID.3 Pro S Tour",
        "VW ID.3 Pro S, EZ 09/2022, 38.000 km, Elektro, Automatik, 150 kW. "
        "Batteriekapazität 77 kWh, Batteriezustand 96%. 28.500 EUR. Händler, 50667 Köln.",
    ),
    (
        "autoscout24", "VW ID. Buzz Pro",
        "VW ID. Buzz Pro, Erstzulassung 2023, 21.000 km, elektrisch, 150 kW, "
        "Akku 77 kWh, SoH 98%. 49.900 €. 20095 Hamburg.",
    ),
    (
        "kleinanzeigen", "VW Golf VII 2.0 TDI Highline DSG",
        "VW Golf 7 2.0 TDI Highline, EZ 03/2016, 142.000 km, Diesel, Automatik (DSG), "
        "110 kW. Scheckheftgepflegt, Händler. 12.490 EUR. 70173 Stuttgart.",
    ),
    (
        "autoscout24", "Hyundai Kona Elektro Trend 64 kWh",
        "Hyundai Kona Elektro, EZ 05/2020, 71.000 km, Elektro, Automatik, 150 kW, "
        "64 kWh Akku, SoH 90%. 19.900 € VB. Privat, 04109 Leipzig.",
    ),
]


def _seed_raw(session: Session) -> None:
    for i, (source, title, text) in enumerate(SAMPLES, 1):
        sid = f"demo-{i}"
        existing = session.exec(
            select(Listing).where(Listing.source == source, Listing.source_id == sid)
        ).first()
        if existing:
            continue
        session.add(
            Listing(
                source=source, source_id=sid, url=f"https://example.com/{source}/{sid}",
                raw_title=title, raw_text=text,
                raw_html_hash=sha256_text(f"{title}\n{text}"),
            )
        )
    session.commit()


async def main() -> None:
    config._settings = Settings(
        ai_provider="ollama", ai_disabled=False, scheduler_enabled=False,
        haiku_concurrency=1,  # local single-GPU model: serialize calls
    )
    init_db()
    state = build_state(config._settings)
    print(f"extractor enabled={state.extractor.enabled} "
          f"(provider={config._settings.ai_provider}, model={config._settings.ollama_model})")

    with Session(get_engine()) as session:
        _seed_raw(session)
        norm = await normalize_pending(session, state.extractor)
        cat = categorize_active(session)
        print(f"normalized={norm.normalized} failed={norm.failed} "
              f"cost=${norm.cost_usd:.4f} | categorized={cat.categorized}\n")

        rows = session.exec(select(Listing).order_by(Listing.source_id)).all()
        for r in rows:
            print(
                f"  [{r.source_id}] {r.make} {r.model} {r.variant or ''} | "
                f"{r.fuel} | {r.battery_kwh} kWh | SoH {r.battery_soh_pct} | "
                f"{r.year} | {r.mileage_km} km | {r.price} € | {r.seller_type}"
            )

    await state.firecrawl.aclose()


if __name__ == "__main__":
    asyncio.run(main())
