import { useEffect, useState } from "react";
import {
  createModelGuide,
  evaluateListing,
  getListing,
  setFavorite,
  setListingModel,
} from "../api/client";
import type { AiEvaluation, Listing } from "../types";
import { formatKm, formatPrice, formatYear } from "../lib/format";
import { DealScoreBadge } from "./DealScoreBadge";

const VERDICT_STYLE: Record<AiEvaluation["deal_verdict"], string> = {
  good: "bg-emerald-100 text-emerald-700",
  fair: "bg-slate-100 text-slate-600",
  overpriced: "bg-rose-100 text-rose-700",
};

interface ListingDetailDrawerProps {
  listingId: number;
  onClose: () => void;
  onOpenGuide?: (model: string, make?: string) => void;
}

export function ListingDetailDrawer({
  listingId,
  onClose,
  onOpenGuide,
}: ListingDetailDrawerProps) {
  const [listing, setListing] = useState<Listing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [isFavorite, setIsFavorite] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setListing(null);
    setError(null);
    getListing(listingId)
      .then((l) => {
        if (cancelled) return;
        setListing(l);
        setIsFavorite(l.is_favorite);
      })
      .catch((e: unknown) =>
        !cancelled && setError(e instanceof Error ? e.message : "Failed to load"),
      );
    return () => {
      cancelled = true;
    };
  }, [listingId]);

  const onToggleFavorite = async () => {
    const next = !isFavorite;
    setIsFavorite(next);
    try {
      await setFavorite(listingId, next);
    } catch (e) {
      setIsFavorite(!next);
      setError(e instanceof Error ? e.message : "Favorite update failed");
    }
  };

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
            {listing && (
              <span className="mr-2 font-mono text-xs font-normal text-slate-400">
                #{listing.id}
              </span>
            )}
            {listing
              ? listing.make && listing.model
                ? `${listing.make} ${listing.model} ${listing.variant ?? ""}`
                : listing.raw_title
              : "Loading…"}
          </h3>
          <div className="flex shrink-0 items-center gap-1">
            {listing && (
              <button
                onClick={onToggleFavorite}
                className={`rounded p-1 text-lg leading-none ${
                  isFavorite
                    ? "text-amber-400"
                    : "text-slate-300 hover:bg-slate-100 hover:text-amber-300"
                }`}
                aria-label={`Favorite ${listing.make ?? ""} ${listing.model ?? listing.raw_title}`}
                aria-pressed={isFavorite}
              >
                {isFavorite ? "★" : "☆"}
              </button>
            )}
            <button
              onClick={onClose}
              className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              aria-label="Close"
            >
              ✕
            </button>
          </div>
        </header>

        {error && (
          <div className="m-6 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
            {error}
          </div>
        )}

        {listing && (
          <div className="space-y-6 px-6 py-5">
            <SpecGrid listing={listing} />
            <ModelSection
              listing={listing}
              onOpenGuide={onOpenGuide}
              onReassign={async (model) => {
                const prev = listing;
                // Optimistic update.
                setListing({ ...listing, model, model_locked: true });
                try {
                  setListing(await setListingModel(listing.id, model));
                } catch (e) {
                  setListing(prev);
                  setError(e instanceof Error ? e.message : "Model reassign failed");
                }
              }}
            />
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

function ModelSection({
  listing,
  onOpenGuide,
  onReassign,
}: {
  listing: Listing;
  onOpenGuide?: (model: string, make?: string) => void;
  onReassign: (model: string) => void | Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(listing.model ?? "");
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const onCreateGuide = async () => {
    if (!listing.model) return;
    setCreating(true);
    setCreateError(null);
    try {
      await createModelGuide(listing.make ?? "", listing.model);
      setCreated(true);
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : "Could not start generation.");
    } finally {
      setCreating(false);
    }
  };

  const save = async () => {
    const value = draft.trim();
    if (!value || value === listing.model) {
      setEditing(false);
      return;
    }
    await onReassign(value);
    setEditing(false);
  };

  return (
    <div className="rounded-lg border border-slate-200 p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Model</p>
        {listing.model_locked && (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-700">
            manual
          </span>
        )}
      </div>

      <div className="mb-3 flex items-center gap-2 text-sm">
        <span className="font-medium text-slate-800">
          {[listing.make, listing.model].filter(Boolean).join(" ") || "—"}
        </span>
        {listing.model && onOpenGuide && (
          <button
            type="button"
            onClick={() => onOpenGuide(listing.model!, listing.make ?? undefined)}
            className="rounded-md border border-sky-300 px-2 py-0.5 text-xs font-medium text-sky-700 hover:bg-sky-50"
          >
            📖 Model guide
          </button>
        )}
        {listing.model && (
          <button
            type="button"
            onClick={onCreateGuide}
            disabled={creating || created}
            className="rounded-md border border-slate-300 px-2 py-0.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            {created ? "Guide queued ✓" : creating ? "Creating…" : "Create guide"}
          </button>
        )}
      </div>

      {createError && <p className="mb-2 text-xs text-rose-600">{createError}</p>}

      {editing ? (
        <div className="flex items-center gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            aria-label="Reassign model"
            className="w-40 rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-700"
          />
          <button
            type="button"
            onClick={save}
            className="rounded-md bg-sky-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-sky-700"
          >
            Save
          </button>
          <button
            type="button"
            onClick={() => {
              setDraft(listing.model ?? "");
              setEditing(false);
            }}
            className="text-xs font-medium text-slate-500 hover:text-slate-700"
          >
            Cancel
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => {
            setDraft(listing.model ?? "");
            setEditing(true);
          }}
          className="text-xs font-medium text-slate-500 hover:text-slate-700"
        >
          Reassign model
        </button>
      )}
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
