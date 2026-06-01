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
  enabled: true,
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
    if (url.includes("/api/search/nl") && method === "POST") {
      return new Response(
        JSON.stringify({
          query: "Audi A4",
          filters: { make: "Audi", model: "A4" },
          ranking: [],
          rationale: "",
          results: [],
          total: 0,
        }),
        { status: 200 },
      );
    }
    if (url.includes("/run") && method === "POST") {
      return new Response(JSON.stringify({ status: "scheduled" }), { status: 202 });
    }
    if (method === "PUT") {
      return new Response(JSON.stringify({ ...existing }), { status: 200 });
    }
    return new Response("{}", { status: 200 });
  });
}

test("lists existing saved searches with criteria summary", async () => {
  mockApi([existing]);
  render(<SavedSearches />);
  await waitFor(() => expect(screen.getByText("VW Golf budget")).toBeInTheDocument());
  expect(screen.getByText(/Volkswagen Golf/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Run now/ })).toBeInTheDocument();
});

test("Run now posts to the run endpoint without any secret header", async () => {
  const fetchSpy = mockApi([existing]);
  render(<SavedSearches />);
  await waitFor(() => screen.getByRole("button", { name: /Run now/ }));
  fireEvent.click(screen.getByRole("button", { name: /Run now/ }));
  await waitFor(() =>
    expect(
      fetchSpy.mock.calls.some(
        ([u, i]) =>
          String(u).includes("/run") &&
          i?.method === "POST" &&
          !(i?.headers as Record<string, string> | undefined)?.["X-Cron-Secret"],
      ),
    ).toBe(true),
  );
});

test("shows empty state when there are none", async () => {
  mockApi([]);
  render(<SavedSearches />);
  await waitFor(() =>
    expect(screen.getByText(/No saved searches yet/)).toBeInTheDocument(),
  );
});

test("submitting a text query translates then posts a new search", async () => {
  const fetchSpy = mockApi([]);
  render(<SavedSearches />);
  await waitFor(() => screen.getByText(/No saved searches yet/));
  fireEvent.change(screen.getByLabelText(/Search query/), {
    target: { value: "Audi A4" },
  });
  fireEvent.change(screen.getByLabelText(/Name/), {
    target: { value: "A4 deals" },
  });
  fireEvent.click(screen.getByRole("button", { name: /Add search/ }));
  await waitFor(() => {
    const calls = fetchSpy.mock.calls;
    // translate first, then create
    expect(calls.some(([u]) => String(u).includes("/api/search/nl"))).toBe(true);
    expect(
      calls.some(
        ([u, i]) => String(u).endsWith("/api/saved-searches") && i?.method === "POST",
      ),
    ).toBe(true);
  });
});
