import { useState } from "react";
import { useDebounce } from "../hooks/useDebounce";
import { useListings } from "../hooks/useListings";
import { ListingsTable, type TableFilters } from "../components/ListingsTable";
import { RefreshControls } from "../components/RefreshControls";
import type { ListingQuery } from "../types";

function toQuery(f: TableFilters): ListingQuery {
  return {
    model: f.model || undefined,
    source: f.source || undefined,
    trim: f.trim || undefined,
    max_price: f.max_price,
    max_km: f.max_km,
  };
}

export function Dashboard() {
  const [filters, setFilters] = useState<TableFilters>({});
  const debouncedFilters = useDebounce(filters, 300);
  const query: ListingQuery = toQuery(debouncedFilters);
  const { data, loading, error, reload } = useListings(query);

  const items = data ?? [];
  const hasFilters = Object.values(filters).some((v) => v !== undefined && v !== "");

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-3 text-lg font-semibold text-slate-800">
          VW ID.3 / ID.4 offers
          <span className="text-sm font-normal text-slate-400">{items.length} found</span>
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
          <RefreshControls onComplete={reload} />
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {error}
        </div>
      )}
      {loading && !data && <div className="text-slate-400">Loading…</div>}

      <ListingsTable items={items} filters={filters} onFilterChange={setFilters} />
    </section>
  );
}
