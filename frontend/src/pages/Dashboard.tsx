import { useState } from "react";
import { useListings } from "../hooks/useListings";
import { ListingsTable } from "../components/ListingsTable";
import { RefreshControls } from "../components/RefreshControls";
import type { SortField } from "../types";

const SORTS: { value: SortField; label: string }[] = [
  { value: "scraped_at", label: "Newest" },
  { value: "price", label: "Price" },
  { value: "year", label: "Year" },
  { value: "mileage_km", label: "Mileage" },
];

export function Dashboard() {
  const [sort, setSort] = useState<SortField>("scraped_at");
  const order = sort === "scraped_at" || sort === "year" ? "desc" : "asc";
  const { data, loading, error, reload } = useListings({ sort, order, page_size: 50 });

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-slate-800">
          Listings
          {data && (
            <span className="ml-2 text-sm font-normal text-slate-400">
              {data.total} found
            </span>
          )}
        </h2>
        <div className="flex items-center gap-4">
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
          <RefreshControls onComplete={reload} />
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {error}
        </div>
      )}
      {loading && !data && <div className="text-slate-400">Loading…</div>}
      {data && <ListingsTable items={data.items} />}
    </section>
  );
}
