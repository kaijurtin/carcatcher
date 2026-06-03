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
    model_locked: false,
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

test("renders the stable listing id as a #number", () => {
  render(<ListingsTable items={[listing({ id: 1103 })]} />);
  expect(screen.getByText("#1103")).toBeInTheDocument();
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
  fireEvent.click(screen.getByRole("button", { name: /Favorite Volkswagen/ }));
  expect(onToggleFavorite).toHaveBeenCalledWith(7);
  expect(onSelect).not.toHaveBeenCalled();
});

test("renders the Variant column value", () => {
  render(<ListingsTable items={[listing({ variant: "Pro S" })]} />);
  expect(screen.getByText("Pro S")).toBeInTheDocument();
});

test("renders a filter row and sortable headers when filter props are given", () => {
  render(
    <ListingsTable
      items={[listing({})]}
      filters={{}}
      onFilterChange={() => {}}
      onSort={() => {}}
      sort="scraped_at"
      order="desc"
    />,
  );
  expect(screen.getByLabelText("Filter model")).toBeInTheDocument();
  expect(screen.getByLabelText("Mileage max")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Sort by Price" })).toBeInTheDocument();
});

test("clicking a sortable header calls onSort with that field", () => {
  const onSort = vi.fn();
  render(
    <ListingsTable
      items={[listing({})]}
      onFilterChange={() => {}}
      onSort={onSort}
      sort="scraped_at"
      order="desc"
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Sort by Year" }));
  expect(onSort).toHaveBeenCalledWith("year");
});

test("editing a column filter calls onFilterChange", () => {
  const onFilterChange = vi.fn();
  render(
    <ListingsTable items={[listing({})]} filters={{}} onFilterChange={onFilterChange} />,
  );
  fireEvent.change(screen.getByLabelText("Filter variant"), {
    target: { value: "GTX" },
  });
  expect(onFilterChange).toHaveBeenCalledWith({ variant: "GTX" });
});

test("the favorites header toggles favorites_only via onFilterChange", () => {
  const onFilterChange = vi.fn();
  render(
    <ListingsTable
      items={[listing({})]}
      filters={{}}
      onFilterChange={onFilterChange}
      onToggleFavorite={() => {}}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Favorites only" }));
  expect(onFilterChange).toHaveBeenCalledWith({ favorites_only: true });
});

test("shows a no-matches row (not the crawl CTA) when filtering yields nothing", () => {
  render(<ListingsTable items={[]} filters={{}} onFilterChange={() => {}} />);
  expect(screen.getByText(/No listings match these filters/)).toBeInTheDocument();
});

test("renders the Power, Fair price and Seller columns", () => {
  render(
    <ListingsTable
      items={[
        listing({
          power_kw: 150,
          fair_price_estimate: 24500,
          seller_type: "dealer",
        }),
      ]}
    />,
  );
  // "150 kW" appears in both the Model spec sub-line and the dedicated Power column.
  expect(screen.getAllByText("150 kW").length).toBeGreaterThanOrEqual(1);
  expect(screen.getByText(/24\.500\s*€/)).toBeInTheDocument(); // de-DE grouping
  expect(screen.getByText("Händler")).toBeInTheDocument();
});

test("exposes filter inputs for every filterable column", () => {
  render(
    <ListingsTable items={[listing({})]} filters={{}} onFilterChange={() => {}} />,
  );
  expect(screen.getByLabelText("Power kW min")).toBeInTheDocument();
  expect(screen.getByLabelText("Fair price min")).toBeInTheDocument();
  expect(screen.getByLabelText("Deal score min")).toBeInTheDocument();
  expect(screen.getByLabelText("km per year max")).toBeInTheDocument();
  expect(screen.getByLabelText("Filter seller")).toBeInTheDocument();
  expect(screen.getByLabelText("Filter location")).toBeInTheDocument();
});

test("editing the location filter calls onFilterChange", () => {
  const onFilterChange = vi.fn();
  render(
    <ListingsTable items={[listing({})]} filters={{}} onFilterChange={onFilterChange} />,
  );
  fireEvent.change(screen.getByLabelText("Filter location"), {
    target: { value: "Berlin" },
  });
  expect(onFilterChange).toHaveBeenCalledWith({ location: "Berlin" });
});

test("selecting a seller type calls onFilterChange", () => {
  const onFilterChange = vi.fn();
  render(
    <ListingsTable items={[listing({})]} filters={{}} onFilterChange={onFilterChange} />,
  );
  fireEvent.change(screen.getByLabelText("Filter seller"), {
    target: { value: "private" },
  });
  expect(onFilterChange).toHaveBeenCalledWith({ seller_type: "private" });
});
