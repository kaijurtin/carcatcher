import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  battery_kwh: null,
  condition: "used",
  location: "Berlin",
  distance_km: null,
  title: "VW ID.4 Pro",
  tag: null,
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

  it("sets a tag via the API and reloads listings when a tag is picked", async () => {
    const getListings = vi.spyOn(client, "getListings").mockResolvedValue([listing]);
    const setListingTag = vi.spyOn(client, "setListingTag").mockResolvedValue({ ...listing, tag: "star" });
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByText("1 found")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Tag for Pro"), { target: { value: "star" } });

    await waitFor(() => expect(setListingTag).toHaveBeenCalledWith(1, "star"));
    await waitFor(() => expect(getListings).toHaveBeenCalledTimes(2));
  });

  it("shows an error message when setting a tag fails, and does not reload", async () => {
    const getListings = vi.spyOn(client, "getListings").mockResolvedValue([listing]);
    vi.spyOn(client, "setListingTag").mockRejectedValue(new Error("tag update failed"));
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByText("1 found")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Tag for Pro"), { target: { value: "star" } });

    await waitFor(() => expect(screen.getByText("tag update failed")).toBeInTheDocument());
    expect(getListings).toHaveBeenCalledTimes(1); // no reload on failure
  });
});
