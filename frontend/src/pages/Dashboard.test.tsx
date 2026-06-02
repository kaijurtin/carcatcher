import { render, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";

const emptyPage = { items: [], total: 0, page: 1, page_size: 50 };
const emptyFacets = { models: [], variants: [], battery_kwh: null };

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    getListings: vi.fn(() => Promise.resolve(emptyPage)),
    getFacets: vi.fn(() => Promise.resolve(emptyFacets)),
    getSettings: vi.fn(() =>
      Promise.resolve({ ai_enabled: false, ai_configured: false }),
    ),
    getRuns: vi.fn(() => Promise.resolve([])),
  };
});

import { Dashboard } from "./Dashboard";
import { getListings } from "../api/client";

test("queries listings scoped to electric with newest-first default sort", async () => {
  render(<Dashboard />);
  await waitFor(() => expect(getListings).toHaveBeenCalled());
  const query = vi.mocked(getListings).mock.calls[0][0];
  expect(query).toMatchObject({ fuel: "electric", sort: "scraped_at", order: "desc" });
});
