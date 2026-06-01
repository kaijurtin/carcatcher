import { useEffect, useState } from "react";
import { evaluateListing, getListing } from "../api/client";
import type { AiEvaluation, Listing } from "../types";
import { formatKm, formatPrice, formatYear } from "../lib/format";
import { DealScoreBadge } from "./DealScoreBadge";

const VERDICT_STYLE: Record<AiEvaluation["deal_verdict"], string> = {
  good: "bg-emerald-100 text-emerald-700",
  fair: "bg-slate-100 text-slate-600",
  overpriced: "bg-rose-100 text-rose-700",
};

export function ListingDetailDrawer({
  listingId,
  onClose,
}: {
  listingId: number;
  onClose: () => void;
}) {
  const [listing, setListing] = useState<Listing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [evaluating, setEvaluating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setListing(null);
    setError(null);
    getListing(listingId)
      .then((l) => !cancelled && setListing(l))
      .catch((e: unknown) =>
        !cancelled && setError(e instanceof Error ? e.message : "Failed to load"),
      );
    return () => {
      cancelled = true;
    };
  }, [listingId]);

  const onEvaluate = async () => {
    setEvaluating(true);
    setError(null);
    try {
      setListing(await evaluateListing(listingId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Evaluation failed");
    } finally {
      setEvaluating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-slate-900/30" onClick={onClose} />
      <aside className="relative z-50 flex h-full w-full max-w-xl flex-col overflow-y-auto bg-white shadow-xl">
        <header className="flex items-start justify-between border-b border-slate-200 px-6 py-4">
          <h3 className="pr-6 text-lg font-semibold text-slate-900">
            {listing
              ? listing.make && listing.model
                ? `${listing.make} ${listing.model} ${listing.variant ?? ""}`
                : listing.raw_title
              : "Loading…"}
          </h3>
          <button
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            aria-label="Close"
          >
            ✕
          </button>
        </header>

        {error && (
          <div className="m-6 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
            {error}
          </div>
        )}

        {listing && (
          <div className="space-y-6 px-6 py-5">
            <SpecGrid listing={listing} />
            <AiSection
              evaluation={listing.ai_evaluation}
              evaluating={evaluating}
              onEvaluate={onEvaluate}
            />
            <a
              href={listing.url}
              target="_blank"
              rel="noreferrer"
              className="inline-block text-sm font-medium text-sky-600 hover:text-sky-700"
            >
              Open original listing ↗
            </a>
          </div>
        )}
      </aside>
    </div>
  );
}

function SpecGrid({ listing }: { listing: Listing }) {
  const rows: [string, string | JSX.Element][] = [
    ["Price", formatPrice(listing.price, listing.raw_price)],
    ["Deal", <DealScoreBadge key="d" listing={listing} />],
    ["Year", formatYear(listing.year)],
    ["Mileage", formatKm(listing.mileage_km)],
    ["Fuel", listing.fuel ?? "—"],
    ["Transmission", listing.transmission ?? "—"],
    ["Power", listing.power_kw ? `${listing.power_kw} kW` : "—"],
    ...(listing.battery_kwh != null
      ? ([["Battery", `${listing.battery_kwh} kWh`]] as [string, string][])
      : []),
    ...(listing.battery_soh_pct != null
      ? ([["Battery health", `${listing.battery_soh_pct}%`]] as [string, string][])
      : []),
    ["Seller", listing.seller_type ?? "—"],
    ["Location", listing.location_raw ?? "—"],
  ];
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
      {rows.map(([label, value]) => (
        <div key={label} className="flex justify-between border-b border-slate-100 py-1">
          <dt className="text-slate-400">{label}</dt>
          <dd className="font-medium text-slate-800">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function AiSection({
  evaluation,
  evaluating,
  onEvaluate,
}: {
  evaluation: AiEvaluation | null;
  evaluating: boolean;
  onEvaluate: () => void;
}) {
  if (!evaluation) {
    return (
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
        <p className="mb-3 text-sm text-slate-500">
          No AI evaluation yet for this listing.
        </p>
        <button
          onClick={onEvaluate}
          disabled={evaluating}
          className="rounded-md bg-violet-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-violet-700 disabled:bg-slate-300"
        >
          {evaluating ? "Evaluating…" : "Evaluate now"}
        </button>
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-slate-200 p-4">
      <div className="mb-2 flex items-center gap-2">
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-semibold ${VERDICT_STYLE[evaluation.deal_verdict]}`}
        >
          {evaluation.deal_verdict}
        </span>
        <span className="text-xs text-slate-400">
          confidence: {evaluation.confidence}
        </span>
      </div>
      <p className="mb-3 text-sm text-slate-700">{evaluation.summary}</p>
      <BulletList title="Pros" items={evaluation.pros} tone="text-emerald-700" />
      <BulletList title="Cons" items={evaluation.cons} tone="text-slate-600" />
      <BulletList title="Red flags" items={evaluation.red_flags} tone="text-rose-700" />
    </div>
  );
}

function BulletList({
  title,
  items,
  tone,
}: {
  title: string;
  items?: string[];
  tone: string;
}) {
  if (!items || items.length === 0) return null;
  return (
    <div className="mb-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
        {title}
      </p>
      <ul className={`ml-4 list-disc text-sm ${tone}`}>
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
