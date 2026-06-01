import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ListingDetailDrawer } from "./ListingDetailDrawer";
import type { Listing } from "../types";

function listing(over: Partial<Listing>): Listing {
  return {
    id: 7, source: "kleinanzeigen", source_id: "7", url: "https://x/7", status: "active",
    raw_title: "VW Golf", raw_price: "9.000 €", location_raw: "39108 Magdeburg", images: [],
    price: 9000, price_negotiable: false, mileage_km: 100000, year: 2015,
    make: "Volkswagen", model: "Golf", variant: "1.6", fuel: "petrol",
    transmission: "manual", power_kw: 75, battery_kwh: null, battery_soh_pct: null,
    body_type: null, location_city: null,
    location_plz: null, seller_type: "private", fair_price_estimate: 10500,
    deal_score: 0.14, comp_count: 6, ai_evaluation: null, ai_evaluated_at: null,
    first_seen_at: "2026-05-31T00:00:00Z", last_seen_at: "2026-05-31T00:00:00Z",
    scraped_at: "2026-05-31T00:00:00Z",
    ...over,
  };
}

afterEach(() => vi.restoreAllMocks());

function mockFetch(getResp: Listing, evalResp?: Listing) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (init?.method === "POST" && url.includes("/evaluate")) {
      return new Response(JSON.stringify(evalResp ?? getResp), { status: 200 });
    }
    return new Response(JSON.stringify(getResp), { status: 200 });
  });
}

test("renders specs and the evaluate prompt when unevaluated", async () => {
  mockFetch(listing({}));
  render(<ListingDetailDrawer listingId={7} onClose={() => {}} />);
  await waitFor(() =>
    expect(screen.getByText("Volkswagen Golf 1.6")).toBeInTheDocument(),
  );
  expect(screen.getByRole("button", { name: /Evaluate now/ })).toBeInTheDocument();
});

test("evaluate now triggers eval and shows the verdict", async () => {
  const evaluated = listing({
    ai_evaluation: {
      summary: "Good value daily driver.",
      pros: ["TÜV neu"],
      cons: ["High mileage"],
      red_flags: [],
      deal_verdict: "good",
      confidence: "high",
    },
  });
  mockFetch(listing({}), evaluated);

  render(<ListingDetailDrawer listingId={7} onClose={() => {}} />);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: /Evaluate now/ })).toBeInTheDocument(),
  );
  fireEvent.click(screen.getByRole("button", { name: /Evaluate now/ }));

  await waitFor(() =>
    expect(screen.getByText("Good value daily driver.")).toBeInTheDocument(),
  );
  expect(screen.getByText("good")).toBeInTheDocument();
  expect(screen.getByText("TÜV neu")).toBeInTheDocument();
});

test("calls onClose when the close button is clicked", async () => {
  mockFetch(listing({}));
  const onClose = vi.fn();
  render(<ListingDetailDrawer listingId={7} onClose={onClose} />);
  await waitFor(() =>
    expect(screen.getByText("Volkswagen Golf 1.6")).toBeInTheDocument(),
  );
  fireEvent.click(screen.getByLabelText("Close"));
  expect(onClose).toHaveBeenCalled();
});
