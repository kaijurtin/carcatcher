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
  tag: null,
  status: "active",
  first_seen_at: "2026-08-11T00:00:00Z",
  last_seen_at: "2026-08-11T00:00:00Z",
};

const noop = () => {};

describe("ListingsTable", () => {
  it("renders a row per listing", () => {
    render(<ListingsTable items={[listing]} filters={{}} onFilterChange={noop} onTagChange={noop} />);
    expect(screen.getByText("Pro Performance")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: /ID\.4/ })).toBeInTheDocument();
    expect(screen.getByText("34.410 €")).toBeInTheDocument();
  });

  it("shows the empty state when there are no listings", () => {
    render(<ListingsTable items={[]} filters={{}} onFilterChange={noop} onTagChange={noop} />);
    expect(screen.getByText("No listings match these filters.")).toBeInTheDocument();
  });

  it("calls onFilterChange when the trim filter changes", () => {
    const onFilterChange = vi.fn();
    render(<ListingsTable items={[]} filters={{}} onFilterChange={onFilterChange} onTagChange={noop} />);
    fireEvent.change(screen.getByLabelText("Filter trim"), { target: { value: "Pro" } });
    expect(onFilterChange).toHaveBeenCalledWith({ trim: "Pro" });
  });

  it("calls onFilterChange when the max price filter changes", () => {
    const onFilterChange = vi.fn();
    render(<ListingsTable items={[]} filters={{}} onFilterChange={onFilterChange} onTagChange={noop} />);
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
    render(<ListingsTable items={threeListings} filters={{}} onFilterChange={noop} onTagChange={noop} />);

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
    render(<ListingsTable items={threeListings} filters={{}} onFilterChange={noop} onTagChange={noop} />);

    fireEvent.click(screen.getByRole("button", { name: "Sort by Price" }));
    fireEvent.click(screen.getByRole("button", { name: "Sort by Price" })); // now descending by price

    fireEvent.click(screen.getByRole("button", { name: "Sort by Trim" }));
    const order = rowTrims();
    expect(order[0]).toContain("Alpha");
    expect(order[1]).toContain("Bravo");
    expect(order[2]).toContain("Charlie");
  });

  it("sorts null values last regardless of direction", () => {
    render(<ListingsTable items={threeListings} filters={{}} onFilterChange={noop} onTagChange={noop} />);

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

  it("sorts Condition by its displayed label (Gebraucht/Neu), not the raw new/used value", () => {
    const conditionListings: Listing[] = [
      { ...listing, id: 1, trim: "Charlie", condition: "new" }, // displayed "Neu"
      { ...listing, id: 2, trim: "Alpha", condition: "used" }, // displayed "Gebraucht"
    ];
    render(<ListingsTable items={conditionListings} filters={{}} onFilterChange={noop} onTagChange={noop} />);

    fireEvent.click(screen.getByRole("button", { name: "Sort by Condition" }));
    const order = screen.getAllByRole("row").slice(2).map((row) => row.textContent);
    // "Gebraucht" < "Neu" alphabetically, so ascending must show it first,
    // even though the raw value "used" > "new".
    expect(order[0]).toContain("Alpha"); // Gebraucht
    expect(order[1]).toContain("Charlie"); // Neu
  });

  it("shows a tag selector defaulting to no tag", () => {
    render(<ListingsTable items={[listing]} filters={{}} onFilterChange={noop} onTagChange={noop} />);
    expect(screen.getByLabelText("Tag for Pro Performance")).toHaveValue("");
  });

  it("shows the listing's existing tag in the selector", () => {
    render(
      <ListingsTable items={[{ ...listing, tag: "star" }]} filters={{}} onFilterChange={noop} onTagChange={noop} />,
    );
    expect(screen.getByLabelText("Tag for Pro Performance")).toHaveValue("star");
  });

  it("calls onTagChange with the listing id and new tag when a tag is picked", () => {
    const onTagChange = vi.fn();
    render(<ListingsTable items={[listing]} filters={{}} onFilterChange={noop} onTagChange={onTagChange} />);
    fireEvent.change(screen.getByLabelText("Tag for Pro Performance"), { target: { value: "7" } });
    expect(onTagChange).toHaveBeenCalledWith(1, "7");
  });

  it("calls onTagChange with null when the tag is cleared", () => {
    const onTagChange = vi.fn();
    render(
      <ListingsTable
        items={[{ ...listing, tag: "star" }]}
        filters={{}}
        onFilterChange={noop}
        onTagChange={onTagChange}
      />,
    );
    fireEvent.change(screen.getByLabelText("Tag for Pro Performance"), { target: { value: "" } });
    expect(onTagChange).toHaveBeenCalledWith(1, null);
  });
});
