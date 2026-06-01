import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { ListingsTable } from "./ListingsTable";
import type { Listing } from "../types";

function listing(over: Partial<Listing>): Listing {
  return {
    id: 1,
    source: "kleinanzeigen",
    source_id: "1",
    url: "https://example.com/x",
    status: "active",
    raw_title: "VW Golf 1.6",
    raw_price: "4.300 €",
    location_raw: "39108 Magdeburg",
    images: [],
    price: 4300,
    price_negotiable: false,
    mileage_km: 112000,
    year: 2005,
    make: "Volkswagen",
    model: "Golf",
    variant: null,
    fuel: null,
    transmission: null,
    power_kw: null,
    battery_kwh: null,
    battery_soh_pct: null,
    body_type: null,
    location_city: null,
    location_plz: null,
    seller_type: null,
    fair_price_estimate: null,
    deal_score: null,
    comp_count: null,
    ai_evaluation: null,
    ai_evaluated_at: null,
    first_seen_at: "2026-05-31T00:00:00Z",
    last_seen_at: "2026-05-31T00:00:00Z",
    scraped_at: "2026-05-31T00:00:00Z",
    ...over,
  };
}

test("renders empty state when no items", () => {
  render(<ListingsTable items={[]} />);
  expect(screen.getByText(/No listings yet/)).toBeInTheDocument();
});

test("renders a row with formatted price, year and mileage", () => {
  render(<ListingsTable items={[listing({})]} />);
  expect(screen.getByText("Volkswagen Golf")).toBeInTheDocument();
  expect(screen.getByText(/4\.300/)).toBeInTheDocument(); // de-DE EUR grouping
  expect(screen.getByText("2005")).toBeInTheDocument();
  expect(screen.getByText(/112\.000\s*km/)).toBeInTheDocument();
});

test("falls back to raw title when make/model missing", () => {
  render(
    <ListingsTable
      items={[listing({ make: null, model: null, raw_title: "Mystery Car" })]}
    />,
  );
  expect(screen.getByText("Mystery Car")).toBeInTheDocument();
});
