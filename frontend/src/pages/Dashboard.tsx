import { useCallback, useEffect, useState } from "react";
import { useListings } from "../hooks/useListings";
import { useDebounce } from "../hooks/useDebounce";
import { ListingsTable, type TableFilters } from "../components/ListingsTable";
import { ListingDetailDrawer } from "../components/ListingDetailDrawer";
import { RefreshControls } from "../components/RefreshControls";
import { AiToggle } from "../components/AiToggle";
import { RecommendationPanel } from "../components/RecommendationPanel";
import { getFacets, recommend, setFavorite } from "../api/client";
import type {
  FacetCount,
  Listing,
  ListingQuery,
  RecommendResponse,
  SortField,
} from "../types";

/** Sort fields that read most naturally in descending order by default. */
const DESC_DEFAULT = new Set<SortField>(["scraped_at", "year", "deal_score"]);

interface DashboardProps {
  onOpenGuide?: (model: string, make?: string) => void;
}

/** Map the column filters onto /api/listings query params (empties dropped by the client). */
function toQuery(f: TableFilters): Partial<ListingQuery> {
  return {
    model: f.model || undefined,
    variant: f.variant || undefined,
    source: f.source || undefined,
    seller_type: f.seller_type || undefined,
    location: f.location || undefined,
    price_min: f.price_min,
    price_max: f.price_max,
    fair_price_min: f.fair_price_min,
    fair_price_max: f.fair_price_max,
    year_min: f.year_min,
    year_max: f.year_max,
    mileage_max: f.mileage_max,
    km_per_year_max: f.km_per_year_max,
    power_kw_min: f.power_kw_min,
    power_kw_max: f.power_kw_max,
    battery_kwh_min: f.battery_kwh_min,
    battery_kwh_max: f.battery_kwh_max,
    battery_soh_min: f.battery_soh_min,
    deal_score_min: f.deal_score_min,
    favorites_only: f.favorites_only || undefined,
  };
}

export function Dashboard({ onOpenGuide }: DashboardProps) {
  const [filters, setFilters] = useState<TableFilters>({});
  const [sort, setSort] = useState<SortField>("scraped_at");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  // Debounce so typing in a numeric/text header cell doesn't fire a request per keystroke.
  const debouncedFilters = useDebounce(filters, 300);

  // Electric is hard-locked: every query is scoped to fuel=electric.
  const query: ListingQuery = {
    fuel: "electric",
    sort,
    order,
    page_size: 50,
    ...toQuery(debouncedFilters),
  };
  const { data, loading, error, reload } = useListings(query);

  // Model dropdown options: all electric models, independent of other filters.
  const [modelOptions, setModelOptions] = useState<FacetCount[]>([]);
  useEffect(() => {
    getFacets({ fuel: "electric" })
      .then((f) => setModelOptions(f.models))
      .catch(() => setModelOptions([]));
  }, []);

  const onSort = useCallback(
    (field: SortField) => {
      if (sort === field) {
        setOrder((o) => (o === "asc" ? "desc" : "asc"));
      } else {
        setSort(field);
        setOrder(DESC_DEFAULT.has(field) ? "desc" : "asc");
      }
    },
    [sort],
  );

  // Selection + recommendation (the "analyzer").
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [rec, setRec] = useState<RecommendResponse | null>(null);
  const [recBusy, setRecBusy] = useState(false);
  const [recError, setRecError] = useState<string | null>(null);

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

  // Favorites (optimistic) — seeded from loaded items' is_favorite flag.
  const [favoriteIds, setFavoriteIds] = useState<Set<number>>(new Set());
  useEffect(() => {
    const ids = (data?.items ?? []).filter((l) => l.is_favorite).map((l) => l.id);
    setFavoriteIds(new Set(ids));
  }, [data]);

  const onToggleFavorite = useCallback(
    async (id: number) => {
      const willFavorite = !favoriteIds.has(id);
      setFavoriteIds((prev) => {
        const next = new Set(prev);
        if (willFavorite) next.add(id);
        else next.delete(id);
        return next;
      });
      try {
        await setFavorite(id, willFavorite);
      } catch {
        setFavoriteIds((prev) => {
          const next = new Set(prev);
          if (willFavorite) next.delete(id);
          else next.add(id);
          return next;
        });
      }
    },
    [favoriteIds],
  );

  const items: Listing[] = data?.items ?? [];
  const canRecommend = picked.size >= 2 && picked.size <= 8;
  const hasFilters = Object.values(filters).some(
    (v) => v !== undefined && v !== "" && v !== false,
  );

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-3 text-lg font-semibold text-slate-800">
          Opportunities
          <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
            ⚡ Electric only
          </span>
          <span className="text-sm font-normal text-slate-400">
            {data?.total ?? 0} found
          </span>
        </h2>
        <div className="flex flex-wrap items-center justify-end gap-x-4 gap-y-2">
          {hasFilters && (
            <button
              type="button"
              onClick={() => setFilters({})}
              className="text-sm font-medium text-slate-500 hover:text-slate-700"
            >
              Clear filters
            </button>
          )}
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
          <AiToggle />
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

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {error}
        </div>
      )}
      {loading && !data && <div className="text-slate-400">Loading…</div>}

      <ListingsTable
        items={items}
        onSelect={setSelectedId}
        selectedIds={picked}
        onToggleSelect={toggle}
        favoriteIds={favoriteIds}
        onToggleFavorite={onToggleFavorite}
        filters={filters}
        onFilterChange={setFilters}
        modelOptions={modelOptions}
        sort={sort}
        order={order}
        onSort={onSort}
      />

      {selectedId !== null && (
        <ListingDetailDrawer
          listingId={selectedId}
          onClose={() => setSelectedId(null)}
          onOpenGuide={onOpenGuide}
        />
      )}
    </section>
  );
}
