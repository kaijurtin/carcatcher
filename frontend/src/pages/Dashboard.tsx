import { useCallback, useEffect, useState } from "react";
import { useListings } from "../hooks/useListings";
import { ListingsTable } from "../components/ListingsTable";
import { ListingDetailDrawer } from "../components/ListingDetailDrawer";
import { RefreshControls } from "../components/RefreshControls";
import { SearchBar } from "../components/SearchBar";
import { RecommendationPanel } from "../components/RecommendationPanel";
import { createSavedSearch, getSavedSearches, nlSearch, recommend } from "../api/client";
import type {
  Listing,
  NlSearchResponse,
  RecommendResponse,
  SavedSearch,
  SortField,
  StructuredFilters,
} from "../types";

const SORTS: { value: SortField; label: string }[] = [
  { value: "scraped_at", label: "Newest" },
  { value: "deal_score", label: "Best deal" },
  { value: "price", label: "Price" },
  { value: "year", label: "Year" },
  { value: "mileage_km", label: "Mileage" },
];
const DESC_SORTS: SortField[] = ["scraped_at", "year", "deal_score"];

const SOURCES: { value: string; label: string }[] = [
  { value: "", label: "All sources" },
  { value: "kleinanzeigen", label: "Kleinanzeigen" },
  { value: "autoscout24", label: "AutoScout24" },
  { value: "mobilede", label: "mobile.de" },
];

export function Dashboard() {
  const [sort, setSort] = useState<SortField>("scraped_at");
  const [source, setSource] = useState<string>("");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  // Search tabs ("All" = undefined search_id, else a saved search id)
  const [searches, setSearches] = useState<SavedSearch[]>([]);
  const [activeSearch, setActiveSearch] = useState<number | "all">("all");
  useEffect(() => {
    getSavedSearches().then(setSearches).catch(() => setSearches([]));
  }, []);

  const order = DESC_SORTS.includes(sort) ? "desc" : "asc";
  const { data, loading, error, reload } = useListings({
    sort,
    order,
    source: source || undefined,
    search_id: activeSearch === "all" ? undefined : activeSearch,
    page_size: 50,
  });

  // NL search overlay
  const [nl, setNl] = useState<NlSearchResponse | null>(null);
  const [nlLoading, setNlLoading] = useState(false);
  const [nlError, setNlError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // Selection + recommendation
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [rec, setRec] = useState<RecommendResponse | null>(null);
  const [recBusy, setRecBusy] = useState(false);
  const [recError, setRecError] = useState<string | null>(null);

  const runNlSearch = useCallback(async (query: string) => {
    setNlLoading(true);
    setNlError(null);
    setSaved(false);
    try {
      setNl(await nlSearch(query));
    } catch (e) {
      setNlError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setNlLoading(false);
    }
  }, []);

  const toggle = useCallback((id: number) => {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const getRecommendation = useCallback(async () => {
    setRecBusy(true);
    setRecError(null);
    try {
      setRec(await recommend([...picked]));
    } catch (e) {
      setRecError(e instanceof Error ? e.message : "Recommendation failed");
    } finally {
      setRecBusy(false);
    }
  }, [picked]);

  const saveCurrentSearch = useCallback(async () => {
    if (!nl) return;
    const name = window.prompt("Name this saved search:", nl.query)?.trim();
    if (!name) return;
    try {
      await createSavedSearch({
        name,
        criteria: nl.filters as StructuredFilters,
        nl_query: nl.query,
        auto_evaluate: true,
      });
      setSaved(true);
    } catch {
      /* surfaced elsewhere; keep the bar simple */
    }
  }, [nl]);

  const items: Listing[] = nl ? nl.results : (data?.items ?? []);
  const canRecommend = picked.size >= 2 && picked.size <= 8;

  return (
    <section>
      <div className="mb-4">
        <SearchBar
          onSearch={runNlSearch}
          onClear={() => {
            setNl(null);
            setNlError(null);
          }}
          loading={nlLoading}
          active={nl !== null}
        />
      </div>

      {!nl && searches.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-1 border-b border-slate-200">
          <SearchTab label="All" active={activeSearch === "all"} onClick={() => setActiveSearch("all")} />
          {searches.map((s) => (
            <SearchTab
              key={s.id}
              label={s.name}
              active={activeSearch === s.id}
              onClick={() => setActiveSearch(s.id)}
            />
          ))}
        </div>
      )}

      {nlError && (
        <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {nlError}
        </div>
      )}
      {nl && (
        <div className="mb-4 flex items-start justify-between gap-3 rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm text-sky-800">
          <span>
            <span className="font-medium">Interpreted:</span> {nl.rationale}
          </span>
          <button
            onClick={saveCurrentSearch}
            disabled={saved}
            className="shrink-0 rounded-md border border-sky-300 px-2.5 py-1 text-xs font-medium text-sky-700 hover:bg-sky-100 disabled:opacity-50"
          >
            {saved ? "Saved ✓" : "Save this search"}
          </button>
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-slate-800">
          {nl ? "Search results" : "Listings"}
          <span className="ml-2 text-sm font-normal text-slate-400">
            {nl ? nl.total : (data?.total ?? 0)} found
          </span>
        </h2>
        <div className="flex items-center gap-4">
          {picked.size > 0 && (
            <button
              onClick={getRecommendation}
              disabled={!canRecommend || recBusy}
              title={canRecommend ? "" : "Pick 2–8 cars"}
              className="rounded-md bg-violet-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-violet-700 disabled:bg-slate-300"
            >
              {recBusy ? "Thinking…" : `Recommend (${picked.size})`}
            </button>
          )}
          {!nl && (
            <>
              <select
                value={source}
                onChange={(e) => setSource(e.target.value)}
                aria-label="Source"
                className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-700"
              >
                {SOURCES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
              <label className="flex items-center gap-2 text-sm text-slate-500">
                Sort
                <select
                  value={sort}
                  onChange={(e) => setSort(e.target.value as SortField)}
                  className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-700"
                >
                  {SORTS.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </label>
            </>
          )}
          <RefreshControls onComplete={reload} />
        </div>
      </div>

      {recError && (
        <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {recError}
        </div>
      )}
      {rec && (
        <RecommendationPanel
          recommendation={rec.recommendation}
          listings={rec.listings}
          onClose={() => setRec(null)}
        />
      )}

      {error && !nl && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {error}
        </div>
      )}
      {loading && !data && !nl && <div className="text-slate-400">Loading…</div>}
      <ListingsTable
        items={items}
        onSelect={setSelectedId}
        selectedIds={picked}
        onToggleSelect={toggle}
      />

      {selectedId !== null && (
        <ListingDetailDrawer
          listingId={selectedId}
          onClose={() => setSelectedId(null)}
        />
      )}
    </section>
  );
}

function SearchTab({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
        active
          ? "border-sky-600 text-sky-700"
          : "border-transparent text-slate-500 hover:text-slate-800"
      }`}
    >
      {label}
    </button>
  );
}
