import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { DealScoreBadge } from "./DealScoreBadge";
import type { Listing } from "../types";

function listing(over: Partial<Listing>): Listing {
  return {
    id: 1, source: "kleinanzeigen", source_id: "1", url: "u", status: "active",
    raw_title: "VW Golf", raw_price: null, location_raw: null, images: [],
    price: 9000, price_negotiable: false, mileage_km: 100000, year: 2015,
    make: "Volkswagen", model: "Golf", variant: null, fuel: null, transmission: null,
    power_kw: null, battery_kwh: null, battery_soh_pct: null, body_type: null, location_city: null, location_plz: null,
    seller_type: null, fair_price_estimate: 10000, deal_score: 0.1, comp_count: 6,
    ai_evaluation: null, ai_evaluated_at: null,
    first_seen_at: "2026-05-31T00:00:00Z", last_seen_at: "2026-05-31T00:00:00Z",
    scraped_at: "2026-05-31T00:00:00Z",
    ...over,
  };
}

test("shows percent under market for a good deal", () => {
  render(<DealScoreBadge listing={listing({})} />);
  expect(screen.getByText("10% under")).toBeInTheDocument();
});

test("shows percent over for an overpriced listing", () => {
  render(<DealScoreBadge listing={listing({ deal_score: -0.15 })} />);
  expect(screen.getByText("15% over")).toBeInTheDocument();
});

test("shows dash when no estimate", () => {
  render(
    <DealScoreBadge
      listing={listing({ deal_score: null, fair_price_estimate: null })}
    />,
  );
  expect(screen.getByText("—")).toBeInTheDocument();
});
