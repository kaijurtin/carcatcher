import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { SavedSearches } from "./SavedSearches";
import type { SavedSearch } from "../types";

afterEach(() => vi.restoreAllMocks());

const existing: SavedSearch = {
  id: 1,
  name: "VW Golf budget",
  criteria: { make: "Volkswagen", model: "Golf", price_max: 15000 },
  nl_query: null,
  auto_evaluate: true,
  created_at: "2026-05-31T00:00:00Z",
  updated_at: "2026-05-31T00:00:00Z",
};

function mockApi(list: SavedSearch[]) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (url.endsWith("/api/saved-searches") && method === "GET") {
      return new Response(JSON.stringify(list), { status: 200 });
    }
    if (url.endsWith("/api/saved-searches") && method === "POST") {
      return new Response(JSON.stringify({ ...existing, id: 2 }), { status: 201 });
    }
    return new Response("{}", { status: 200 });
  });
}

test("lists existing saved searches with criteria summary", async () => {
  mockApi([existing]);
  render(<SavedSearches />);
  await waitFor(() => expect(screen.getByText("VW Golf budget")).toBeInTheDocument());
  expect(screen.getByText(/Volkswagen Golf/)).toBeInTheDocument();
});

test("shows empty state when there are none", async () => {
  mockApi([]);
  render(<SavedSearches />);
  await waitFor(() =>
    expect(screen.getByText(/No saved searches yet/)).toBeInTheDocument(),
  );
});

test("submitting the form posts a new search", async () => {
  const fetchSpy = mockApi([]);
  render(<SavedSearches />);
  await waitFor(() => screen.getByText(/No saved searches yet/));
  fireEvent.change(screen.getByPlaceholderText("VW Golf budget"), {
    target: { value: "Audi A4" },
  });
  fireEvent.click(screen.getByRole("button", { name: /Add search/ }));
  await waitFor(() =>
    expect(
      fetchSpy.mock.calls.some(
        ([u, i]) => String(u).endsWith("/api/saved-searches") && i?.method === "POST",
      ),
    ).toBe(true),
  );
});
