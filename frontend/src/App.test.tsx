import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import App from "./App";
import type { ListingsPage } from "./types";

const emptyPage: ListingsPage = { items: [], total: 0, page: 1, page_size: 50 };

/** Route fetch by URL so health and listings each get a sensible response. */
function mockApi(health: { status: string }, listings = emptyPage, healthStatus = 200) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes("/api/health")) {
      return new Response(JSON.stringify(health), { status: healthStatus });
    }
    if (url.includes("/api/listings")) {
      return new Response(JSON.stringify(listings), { status: 200 });
    }
    if (url.includes("/api/runs")) {
      return new Response(JSON.stringify([]), { status: 200 });
    }
    return new Response("{}", { status: 404 });
  });
}

afterEach(() => vi.restoreAllMocks());

test("renders the CarCatcher header", () => {
  mockApi({ status: "ok" });
  render(<App />);
  expect(screen.getByText(/CarCatcher/)).toBeInTheDocument();
});

test("shows API healthy when health endpoint returns ok", async () => {
  mockApi({ status: "ok" });
  render(<App />);
  await waitFor(() => expect(screen.getByText("API healthy")).toBeInTheDocument());
});

test("shows API down when health check fails", async () => {
  vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network"));
  render(<App />);
  await waitFor(() => expect(screen.getByText("API down")).toBeInTheDocument());
});

test("renders the empty-state when there are no listings", async () => {
  mockApi({ status: "ok" });
  render(<App />);
  await waitFor(() =>
    expect(screen.getByText(/No listings yet/)).toBeInTheDocument(),
  );
});
