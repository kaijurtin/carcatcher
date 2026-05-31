import type { Listing, Recommendation } from "../types";

export function RecommendationPanel({
  recommendation,
  listings,
  onClose,
}: {
  recommendation: Recommendation;
  listings: Listing[];
  onClose: () => void;
}) {
  const byId = new Map(listings.map((l) => [l.id, l]));
  const topPick = byId.get(recommendation.top_pick_id);
  const ranked = [...recommendation.ranking].sort((a, b) => a.rank - b.rank);

  return (
    <div className="mb-6 rounded-xl border border-violet-200 bg-violet-50 p-5">
      <div className="mb-3 flex items-start justify-between">
        <h3 className="text-base font-semibold text-violet-900">
          🏆 Recommendation
          {topPick && (
            <span className="ml-2 font-normal text-violet-700">
              {topPick.make} {topPick.model} {topPick.variant ?? ""}
            </span>
          )}
        </h3>
        <button
          onClick={onClose}
          className="rounded p-1 text-violet-400 hover:bg-violet-100"
          aria-label="Dismiss recommendation"
        >
          ✕
        </button>
      </div>

      <p className="mb-4 text-sm text-slate-700">{recommendation.summary}</p>

      <ol className="mb-3 space-y-2">
        {ranked.map((r) => {
          const car = byId.get(r.listing_id);
          const isTop = r.listing_id === recommendation.top_pick_id;
          return (
            <li
              key={r.listing_id}
              className={`rounded-lg border p-3 text-sm ${
                isTop
                  ? "border-violet-300 bg-white"
                  : "border-slate-200 bg-white/60"
              }`}
            >
              <span className="font-medium text-slate-800">
                #{r.rank} {car ? `${car.make} ${car.model}` : `Listing ${r.listing_id}`}
              </span>
              <p className="mt-0.5 text-slate-600">{r.reason}</p>
            </li>
          );
        })}
      </ol>

      {recommendation.caveats.length > 0 && (
        <div className="text-xs text-slate-500">
          <span className="font-semibold uppercase tracking-wide">Caveats: </span>
          {recommendation.caveats.join(" · ")}
        </div>
      )}
    </div>
  );
}
