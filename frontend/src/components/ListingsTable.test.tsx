import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
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
    is_favorite: false,
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

test("renders km/Jahr (annualized mileage) and em dash when year missing", () => {
  const fourYearsAgo = new Date().getFullYear() - 4;
  const { rerender } = render(
    <ListingsTable items={[listing({ mileage_km: 100000, year: fourYearsAgo })]} />,
  );
  expect(screen.getByText("25.000/Jahr")).toBeInTheDocument(); // 100000 / 4

  rerender(<ListingsTable items={[listing({ mileage_km: 100000, year: null })]} />);
  // With year null there is no km/Jahr value — a dash is shown instead.
  expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(1);
});

test("falls back to raw title when make/model missing", () => {
  render(
    <ListingsTable
      items={[listing({ make: null, model: null, raw_title: "Mystery Car" })]}
    />,
  );
  expect(screen.getByText("Mystery Car")).toBeInTheDocument();
});

test("renders the Model column as make model variant", () => {
  render(
    <ListingsTable
      items={[listing({ make: "Tesla", model: "Model 3", variant: "Long Range" })]}
    />,
  );
  expect(screen.getByText("Tesla Model 3 Long Range")).toBeInTheDocument();
});

test("renders Battery and SoH columns, with em dash when null", () => {
  render(
    <ListingsTable items={[listing({ battery_kwh: 75, battery_soh_pct: 92 })]} />,
  );
  expect(screen.getByText("75 kWh")).toBeInTheDocument();
  expect(screen.getByText("92%")).toBeInTheDocument();
});

test("shows em dash for Battery and SoH when null", () => {
  render(
    <ListingsTable
      items={[listing({ battery_kwh: null, battery_soh_pct: null })]}
    />,
  );
  // Mileage location and both EV columns render dashes when empty; ensure at least the EV dashes are present.
  expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
});

test("renders the favorite star and reflects favoriteIds", () => {
  render(
    <ListingsTable
      items={[listing({ id: 7 })]}
      favoriteIds={new Set([7])}
      onToggleFavorite={() => {}}
    />,
  );
  const star = screen.getByRole("button", { name: /Favorite/ });
  expect(star).toHaveTextContent("★");
});

test("renders an outline star when not favorited", () => {
  render(
    <ListingsTable
      items={[listing({ id: 7 })]}
      favoriteIds={new Set()}
      onToggleFavorite={() => {}}
    />,
  );
  expect(screen.getByRole("button", { name: /Favorite/ })).toHaveTextContent("☆");
});

test("clicking the star calls onToggleFavorite and not onSelect", () => {
  const onToggleFavorite = vi.fn();
  const onSelect = vi.fn();
  render(
    <ListingsTable
      items={[listing({ id: 7 })]}
      favoriteIds={new Set()}
      onToggleFavorite={onToggleFavorite}
      onSelect={onSelect}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: /Favorite/ }));
  expect(onToggleFavorite).toHaveBeenCalledWith(7);
  expect(onSelect).not.toHaveBeenCalled();
});
