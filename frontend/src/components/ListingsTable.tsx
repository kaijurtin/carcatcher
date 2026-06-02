import type { FacetCount, Listing, SortField } from "../types";
import { formatKm, formatKmPerYear, formatPrice, formatYear } from "../lib/format";
import { DealScoreBadge } from "./DealScoreBadge";

export const SOURCE_LABEL: Record<string, string> = {
  kleinanzeigen: "Kleinanzeigen",
  autoscout24: "AutoScout24",
  mobilede: "mobile.de",
};

const SOURCE_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "All sources" },
  { value: "kleinanzeigen", label: "Kleinanzeigen" },
  { value: "autoscout24", label: "AutoScout24" },
  { value: "mobilede", label: "mobile.de" },
];

/** Column filters that map 1:1 onto the /api/listings query params. */
export interface TableFilters {
  model?: string;
  variant?: string;
  price_min?: number;
  price_max?: number;
  year_min?: number;
  year_max?: number;
  mileage_max?: number;
  battery_kwh_min?: number;
  battery_kwh_max?: number;
  battery_soh_min?: number;
  source?: string;
  favorites_only?: boolean;
}

function specsLine(l: Listing): string {
  const parts = [
    l.transmission === "automatic"
      ? "Automatik"
      : l.transmission === "manual"
        ? "Schaltgetriebe"
        : null,
    l.power_kw ? `${l.power_kw} kW` : null,
  ].filter(Boolean);
  return parts.join(" · ");
}

function modelLine(l: Listing): string {
  return [l.make, l.model, l.variant].filter(Boolean).join(" ") || l.raw_title;
}

function sohColor(pct: number): string {
  if (pct >= 90) return "text-emerald-600";
  if (pct >= 80) return "text-amber-600";
  return "text-slate-600";
}

const num = (v: string): number | undefined =>
  v.trim() === "" ? undefined : Number(v);

interface ListingsTableProps {
  items: Listing[];
  onSelect?: (id: number) => void;
  selectedIds?: Set<number>;
  onToggleSelect?: (id: number) => void;
  favoriteIds?: Set<number>;
  onToggleFavorite?: (id: number) => void;
  /** When provided, a filter row + sortable headers are rendered. */
  filters?: TableFilters;
  onFilterChange?: (next: TableFilters) => void;
  modelOptions?: FacetCount[];
  sort?: SortField;
  order?: "asc" | "desc";
  onSort?: (field: SortField) => void;
}

export function ListingsTable({
  items,
  onSelect,
  selectedIds,
  onToggleSelect,
  favoriteIds,
  onToggleFavorite,
  filters,
  onFilterChange,
  modelOptions = [],
  sort,
  order,
  onSort,
}: ListingsTableProps) {
  const selectable = !!onToggleSelect;
  const favoritable = !!onToggleFavorite;
  const filterable = !!onFilterChange;
  const f = filters ?? {};
  const set = (patch: Partial<TableFilters>) => onFilterChange?.({ ...f, ...patch });

  // Without header filters, an empty list shows the simple call-to-action card.
  if (items.length === 0 && !filterable) {
    return (
      <div className="rounded-lg border border-dashed border-slate-300 p-12 text-center text-slate-500">
        No listings yet. Run a crawl to populate the dashboard.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            {favoritable && (
              <th className="w-8 px-2 py-3">
                {filterable && (
                  <button
                    type="button"
                    onClick={() => set({ favorites_only: !f.favorites_only })}
                    aria-pressed={f.favorites_only ?? false}
                    aria-label="Favorites only"
                    className={f.favorites_only ? "text-amber-400" : "text-slate-300 hover:text-amber-300"}
                  >
                    {f.favorites_only ? "★" : "☆"}
                  </button>
                )}
              </th>
            )}
            {selectable && <th className="w-10 px-4 py-3" />}
            <th className="px-4 py-3 font-medium">#</th>
            <th className="px-4 py-3 font-medium">Model</th>
            <th className="px-4 py-3 font-medium">Variant</th>
            <th className="px-4 py-3 font-medium">Battery</th>
            <SortableHeader label="Mileage" field="mileage_km" sort={sort} order={order} onSort={onSort} />
            <SortableHeader label="Year" field="year" sort={sort} order={order} onSort={onSort} />
            <SortableHeader label="Price" field="price" sort={sort} order={order} onSort={onSort} />
            <SortableHeader label="Deal" field="deal_score" sort={sort} order={order} onSort={onSort} />
            <th className="px-4 py-3 font-medium">SoH</th>
            <th className="px-4 py-3 font-medium">km/Jahr</th>
            <th className="px-4 py-3 font-medium">Source</th>
            <th className="px-4 py-3 font-medium">Location</th>
            <th className="px-4 py-3 font-medium" />
          </tr>
          {filterable && (
            <tr className="border-t border-slate-200 bg-white text-slate-600 normal-case tracking-normal">
              {favoritable && <th className="px-2 py-2" />}
              {selectable && <th className="px-4 py-2" />}
              <th className="px-4 py-2" />
              <th className="px-4 py-2">
                <select
                  aria-label="Filter model"
                  value={f.model ?? ""}
                  onChange={(e) => set({ model: e.target.value || undefined })}
                  className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-normal text-slate-700"
                >
                  <option value="">All models</option>
                  {modelOptions.map((m) => (
                    <option key={m.value} value={m.value}>
                      {m.value} ({m.count})
                    </option>
                  ))}
                </select>
              </th>
              <th className="px-4 py-2">
                <input
                  type="text"
                  aria-label="Filter variant"
                  placeholder="e.g. GTX"
                  value={f.variant ?? ""}
                  onChange={(e) => set({ variant: e.target.value || undefined })}
                  className="w-24 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-normal text-slate-700"
                />
              </th>
              <th className="px-4 py-2">
                <RangeInputs
                  label="Battery kWh"
                  min={f.battery_kwh_min}
                  max={f.battery_kwh_max}
                  onMin={(v) => set({ battery_kwh_min: v })}
                  onMax={(v) => set({ battery_kwh_max: v })}
                />
              </th>
              <th className="px-4 py-2">
                <input
                  type="number"
                  inputMode="numeric"
                  aria-label="Mileage max"
                  placeholder="max"
                  value={f.mileage_max ?? ""}
                  onChange={(e) => set({ mileage_max: num(e.target.value) })}
                  className="w-20 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-normal text-slate-700"
                />
              </th>
              <th className="px-4 py-2">
                <RangeInputs
                  label="Year"
                  min={f.year_min}
                  max={f.year_max}
                  onMin={(v) => set({ year_min: v })}
                  onMax={(v) => set({ year_max: v })}
                  width="w-16"
                />
              </th>
              <th className="px-4 py-2">
                <RangeInputs
                  label="Price"
                  min={f.price_min}
                  max={f.price_max}
                  onMin={(v) => set({ price_min: v })}
                  onMax={(v) => set({ price_max: v })}
                />
              </th>
              <th className="px-4 py-2" />
              <th className="px-4 py-2">
                <input
                  type="number"
                  inputMode="numeric"
                  aria-label="Battery SoH min"
                  placeholder="min %"
                  value={f.battery_soh_min ?? ""}
                  onChange={(e) => set({ battery_soh_min: num(e.target.value) })}
                  className="w-16 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-normal text-slate-700"
                />
              </th>
              <th className="px-4 py-2" />
              <th className="px-4 py-2">
                <select
                  aria-label="Filter source"
                  value={f.source ?? ""}
                  onChange={(e) => set({ source: e.target.value || undefined })}
                  className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-normal text-slate-700"
                >
                  {SOURCE_OPTIONS.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </th>
              <th className="px-4 py-2" />
              <th className="px-4 py-2" />
            </tr>
          )}
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.length === 0 ? (
            <tr>
              <td colSpan={16} className="px-4 py-12 text-center text-slate-500">
                No listings match these filters.
              </td>
            </tr>
          ) : (
            items.map((l) => (
              <tr
                key={l.id}
                onClick={() => onSelect?.(l.id)}
                className={`hover:bg-slate-50 ${onSelect ? "cursor-pointer" : ""}`}
              >
                {favoritable && (
                  <td className="px-2 py-3" onClick={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onToggleFavorite?.(l.id);
                      }}
                      aria-label={`Favorite ${l.make ?? ""} ${l.model ?? l.raw_title}`}
                      aria-pressed={favoriteIds?.has(l.id) ?? false}
                      className={`text-lg leading-none ${
                        favoriteIds?.has(l.id) ? "text-amber-400" : "text-slate-300 hover:text-amber-300"
                      }`}
                    >
                      {favoriteIds?.has(l.id) ? "★" : "☆"}
                    </button>
                  </td>
                )}
                {selectable && (
                  <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selectedIds?.has(l.id) ?? false}
                      onChange={() => onToggleSelect?.(l.id)}
                      aria-label={`Select ${l.make ?? ""} ${l.model ?? l.raw_title}`}
                      className="h-4 w-4 accent-violet-600"
                    />
                  </td>
                )}
                <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-slate-400">
                  #{l.id}
                </td>
                <td className="max-w-md px-4 py-3">
                  <span className="line-clamp-1 font-medium text-slate-900">
                    {modelLine(l)}
                  </span>
                  {l.make && specsLine(l) && (
                    <span className="line-clamp-1 text-xs text-slate-400">
                      {specsLine(l)}
                    </span>
                  )}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                  {l.variant ?? "—"}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                  {l.battery_kwh ? `${l.battery_kwh} kWh` : "—"}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                  {formatKm(l.mileage_km)}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                  {formatYear(l.year)}
                </td>
                <td className="whitespace-nowrap px-4 py-3 font-semibold text-slate-900">
                  {formatPrice(l.price, l.raw_price)}
                  {l.price_negotiable && (
                    <span className="ml-1 text-xs font-normal text-slate-400">VB</span>
                  )}
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <DealScoreBadge listing={l} />
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  {l.battery_soh_pct != null ? (
                    <span className={sohColor(l.battery_soh_pct)}>
                      {l.battery_soh_pct}%
                    </span>
                  ) : (
                    <span className="text-slate-600">—</span>
                  )}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                  {formatKmPerYear(l.mileage_km, l.year)}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-500">
                  {SOURCE_LABEL[l.source] ?? l.source}
                </td>
                <td className="max-w-[12rem] px-4 py-3 text-slate-600">
                  <span className="line-clamp-1">{l.location_raw ?? "—"}</span>
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <a
                    href={l.url}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="text-sm font-medium text-sky-600 hover:text-sky-700"
                  >
                    View ↗
                  </a>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function SortableHeader({
  label,
  field,
  sort,
  order,
  onSort,
}: {
  label: string;
  field: SortField;
  sort?: SortField;
  order?: "asc" | "desc";
  onSort?: (field: SortField) => void;
}) {
  if (!onSort) {
    return <th className="px-4 py-3 font-medium">{label}</th>;
  }
  const active = sort === field;
  const arrow = active ? (order === "asc" ? " ▲" : " ▼") : "";
  return (
    <th className="px-4 py-3 font-medium">
      <button
        type="button"
        onClick={() => onSort(field)}
        aria-label={`Sort by ${label}`}
        className={`uppercase tracking-wide ${active ? "text-slate-800" : "text-slate-500 hover:text-slate-700"}`}
      >
        {label}
        {arrow}
      </button>
    </th>
  );
}

function RangeInputs({
  label,
  min,
  max,
  onMin,
  onMax,
  width = "w-20",
}: {
  label: string;
  min?: number;
  max?: number;
  onMin: (v: number | undefined) => void;
  onMax: (v: number | undefined) => void;
  width?: string;
}) {
  return (
    <span className="flex items-center gap-1">
      <input
        type="number"
        inputMode="numeric"
        aria-label={`${label} min`}
        placeholder="min"
        value={min ?? ""}
        onChange={(e) => onMin(num(e.target.value))}
        className={`${width} rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-normal text-slate-700`}
      />
      <span className="text-slate-400">–</span>
      <input
        type="number"
        inputMode="numeric"
        aria-label={`${label} max`}
        placeholder="max"
        value={max ?? ""}
        onChange={(e) => onMax(num(e.target.value))}
        className={`${width} rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-normal text-slate-700`}
      />
    </span>
  );
}
