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
});
