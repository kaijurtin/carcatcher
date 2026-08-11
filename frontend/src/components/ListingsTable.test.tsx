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
    expect(screen.getByRole("cell", { name: /ID\.4/ })).toBeInTheDocument();
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

  const threeListings: Listing[] = [
    { ...listing, id: 1, trim: "Charlie", price_eur: 30000, location: "Berlin" },
    { ...listing, id: 2, trim: "Alpha", price_eur: 10000, location: null },
    { ...listing, id: 3, trim: "Bravo", price_eur: 20000, location: "Aachen" },
  ];

  function rowTrims() {
    return screen.getAllByRole("row").slice(2).map((row) => row.textContent);
  }

  it("sorts ascending on first header click, descending on second click", () => {
    render(<ListingsTable items={threeListings} filters={{}} onFilterChange={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: "Sort by Price" }));
    const ascOrder = rowTrims();
    expect(ascOrder[0]).toContain("Alpha"); // 10000
    expect(ascOrder[1]).toContain("Bravo"); // 20000
    expect(ascOrder[2]).toContain("Charlie"); // 30000

    fireEvent.click(screen.getByRole("button", { name: "Sort by Price" }));
    const descOrder = rowTrims();
    expect(descOrder[0]).toContain("Charlie"); // 30000
    expect(descOrder[1]).toContain("Bravo"); // 20000
    expect(descOrder[2]).toContain("Alpha"); // 10000
  });

  it("switches sort field and resets to ascending when a different header is clicked", () => {
    render(<ListingsTable items={threeListings} filters={{}} onFilterChange={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: "Sort by Price" }));
    fireEvent.click(screen.getByRole("button", { name: "Sort by Price" })); // now descending by price

    fireEvent.click(screen.getByRole("button", { name: "Sort by Trim" }));
    const order = rowTrims();
    expect(order[0]).toContain("Alpha");
    expect(order[1]).toContain("Bravo");
    expect(order[2]).toContain("Charlie");
  });

  it("sorts null values last regardless of direction", () => {
    render(<ListingsTable items={threeListings} filters={{}} onFilterChange={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: "Sort by Location" }));
    let order = rowTrims();
    expect(order[0]).toContain("Bravo"); // Aachen
    expect(order[1]).toContain("Charlie"); // Berlin
    expect(order[2]).toContain("Alpha"); // null location, last

    fireEvent.click(screen.getByRole("button", { name: "Sort by Location" }));
    order = rowTrims();
    expect(order[0]).toContain("Charlie"); // Berlin
    expect(order[1]).toContain("Bravo"); // Aachen
    expect(order[2]).toContain("Alpha"); // null location, still last
  });
});
