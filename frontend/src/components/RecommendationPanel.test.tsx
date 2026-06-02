import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { RecommendationPanel } from "./RecommendationPanel";
import type { Listing, Recommendation } from "../types";

function car(id: number, make: string, model: string): Listing {
  return {
    id, source: "kleinanzeigen", source_id: String(id), url: "u", status: "active",
    raw_title: `${make} ${model}`, raw_price: null, location_raw: null, images: [],
    price: 9000, price_negotiable: false, mileage_km: 100000, year: 2015,
    make, model, variant: null, fuel: null, transmission: null, power_kw: null,
    battery_kwh: null, battery_soh_pct: null,
    body_type: null, location_city: null, location_plz: null, seller_type: null,
    fair_price_estimate: 10000, deal_score: 0.1, comp_count: 6, ai_evaluation: null,
    ai_evaluated_at: null, is_favorite: false, model_locked: false, first_seen_at: "x", last_seen_at: "x", scraped_at: "x",
  };
}

const recommendation: Recommendation = {
  top_pick_id: 2,
  summary: "The BMW wins on long-term value.",
  ranking: [
    { listing_id: 2, rank: 1, reason: "Lower risk, full history." },
    { listing_id: 1, rank: 2, reason: "Cheaper but higher mileage." },
  ],
  caveats: ["Verify service book"],
};

test("renders top pick, summary, ranked reasons and caveats", () => {
  render(
    <RecommendationPanel
      recommendation={recommendation}
      listings={[car(1, "Volkswagen", "Golf"), car(2, "BMW", "3er")]}
      onClose={() => {}}
    />,
  );
  expect(screen.getAllByText(/BMW 3er/).length).toBeGreaterThan(0);
  expect(screen.getByText("The BMW wins on long-term value.")).toBeInTheDocument();
  expect(screen.getByText("Lower risk, full history.")).toBeInTheDocument();
  expect(screen.getByText(/Verify service book/)).toBeInTheDocument();
});

test("calls onClose when dismissed", () => {
  const onClose = vi.fn();
  render(
    <RecommendationPanel
      recommendation={recommendation}
      listings={[car(1, "Volkswagen", "Golf"), car(2, "BMW", "3er")]}
      onClose={onClose}
    />,
  );
  fireEvent.click(screen.getByLabelText("Dismiss recommendation"));
  expect(onClose).toHaveBeenCalled();
});
