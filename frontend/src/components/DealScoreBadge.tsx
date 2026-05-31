import type { Listing } from "../types";

/** Visualizes deal_score: positive = below fair (good), negative = above (pricey). */
export function DealScoreBadge({ listing }: { listing: Listing }) {
  const { deal_score, comp_count, fair_price_estimate } = listing;

  if (deal_score == null || fair_price_estimate == null) {
    return (
      <span className="text-xs text-slate-300" title="Not enough comparable listings">
        —
      </span>
    );
  }

  const pct = Math.round(deal_score * 100);
  const tone =
    deal_score >= 0.08
      ? "bg-emerald-100 text-emerald-700"
      : deal_score <= -0.08
        ? "bg-rose-100 text-rose-700"
        : "bg-slate-100 text-slate-600";
  const label = pct > 0 ? `${pct}% under` : pct < 0 ? `${-pct}% over` : "at market";

  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}
      title={`Fair ≈ €${fair_price_estimate.toLocaleString("de-DE")} (${comp_count} comparables)`}
    >
      {label}
    </span>
  );
}
