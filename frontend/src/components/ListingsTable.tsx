import { useState } from "react";
import type { Listing } from "../types";
import { formatKm, formatPrice, formatYear } from "../lib/format";

export const SOURCE_LABEL: Record<string, string> = {
  vw: "VW.de",
  autoscout24: "AutoScout24",
};

const SOURCE_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "All sources" },
  { value: "vw", label: "VW.de" },
  { value: "autoscout24", label: "AutoScout24" },
];

const MODEL_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "ID.3 + ID.4" },
  { value: "id3", label: "ID.3" },
  { value: "id4", label: "ID.4" },
];

const MODEL_LABEL: Record<string, string> = { id3: "ID.3", id4: "ID.4" };

const TAG_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "—" },
  { value: "star", label: "★" },
  { value: "plus", label: "+" },
  { value: "minus", label: "−" },
  ...Array.from({ length: 10 }, (_, i) => ({ value: String(i + 1), label: String(i + 1) })),
];

export interface TableFilters {
  model?: string;
  source?: string;
  max_price?: number;
  max_km?: number;
  trim?: string;
}

const num = (v: string): number | undefined => (v.trim() === "" ? undefined : Number(v));

type SortField =
  | "model"
  | "trim"
  | "price_eur"
  | "mileage_km"
  | "year"
  | "power_kw"
  | "condition"
  | "location"
  | "source";

interface SortState {
  field: SortField;
  direction: "asc" | "desc";
}

const TEXT_SORT_FIELDS = new Set<SortField>(["model", "trim", "condition", "location", "source"]);

const CONDITION_LABEL: Record<string, string> = { new: "Neu", used: "Gebraucht" };

// Condition sorts by its displayed label, not the raw "new"/"used" value, so
// ascending/descending order matches what the user actually sees in the cell.
function sortValue(item: Listing, field: SortField): unknown {
  if (field === "condition") {
    return CONDITION_LABEL[item.condition] ?? item.condition;
  }
  return item[field];
}

function compareValues(av: unknown, bv: unknown, isText: boolean, direction: "asc" | "desc"): number {
  if (av == null && bv == null) return 0;
  if (av == null) return 1; // nulls always sort last, regardless of direction
  if (bv == null) return -1;
  const cmp = isText
    ? String(av).localeCompare(String(bv), "de")
    : (av as number) - (bv as number);
  return direction === "asc" ? cmp : -cmp;
}

function sortListings(items: Listing[], sort: SortState | null): Listing[] {
  if (!sort) return items;
  const isText = TEXT_SORT_FIELDS.has(sort.field);
  return [...items].sort((a, b) => compareValues(sortValue(a, sort.field), sortValue(b, sort.field), isText, sort.direction));
}

interface ListingsTableProps {
  items: Listing[];
  filters: TableFilters;
  onFilterChange: (next: TableFilters) => void;
  onTagChange: (id: number, tag: string | null) => void;
}

export function ListingsTable({ items, filters, onFilterChange, onTagChange }: ListingsTableProps) {
  const f = filters;
  const set = (patch: Partial<TableFilters>) => onFilterChange({ ...f, ...patch });

  const [sort, setSort] = useState<SortState | null>(null);
  const onSort = (field: SortField) => {
    setSort((prev) =>
      prev?.field === field ? { field, direction: prev.direction === "asc" ? "desc" : "asc" } : { field, direction: "asc" },
    );
  };
  const sortedItems = sortListings(items, sort);

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <SortableHeader label="Model" field="model" sort={sort} onSort={onSort} />
            <SortableHeader label="Trim" field="trim" sort={sort} onSort={onSort} />
            <SortableHeader label="Price" field="price_eur" sort={sort} onSort={onSort} />
            <SortableHeader label="KM" field="mileage_km" sort={sort} onSort={onSort} />
            <SortableHeader label="Year" field="year" sort={sort} onSort={onSort} />
            <SortableHeader label="Power" field="power_kw" sort={sort} onSort={onSort} />
            <SortableHeader label="Condition" field="condition" sort={sort} onSort={onSort} />
            <SortableHeader label="Location" field="location" sort={sort} onSort={onSort} />
            <SortableHeader label="Source" field="source" sort={sort} onSort={onSort} />
            <th className="px-4 py-3 font-medium">Tag</th>
            <th className="px-4 py-3 font-medium" />
          </tr>
          <tr className="border-t border-slate-200 bg-white text-slate-600 normal-case tracking-normal">
            <th className="px-4 py-2">
              <select
                aria-label="Filter model"
                value={f.model ?? ""}
                onChange={(e) => set({ model: e.target.value || undefined })}
                className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-normal text-slate-700"
              >
                {MODEL_OPTIONS.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
            </th>
            <th className="px-4 py-2">
              <input
                type="text"
                aria-label="Filter trim"
                placeholder="contains, e.g. Pro"
                value={f.trim ?? ""}
                onChange={(e) => set({ trim: e.target.value || undefined })}
                className="w-32 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-normal text-slate-700"
              />
            </th>
            <th className="px-4 py-2">
              <input
                type="number"
                inputMode="numeric"
                aria-label="Max price"
                placeholder="max €"
                value={f.max_price ?? ""}
                onChange={(e) => set({ max_price: num(e.target.value) })}
                className="w-24 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-normal text-slate-700"
              />
            </th>
            <th className="px-4 py-2">
              <input
                type="number"
                inputMode="numeric"
                aria-label="Max km"
                placeholder="max km"
                value={f.max_km ?? ""}
                onChange={(e) => set({ max_km: num(e.target.value) })}
                className="w-24 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-normal text-slate-700"
              />
            </th>
            <th className="px-4 py-2" />
            <th className="px-4 py-2" />
            <th className="px-4 py-2" />
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
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.length === 0 ? (
            <tr>
              <td colSpan={11} className="px-4 py-12 text-center text-slate-500">
                No listings match these filters.
              </td>
            </tr>
          ) : (
            sortedItems.map((l) => (
              <tr key={l.id} className="hover:bg-slate-50">
                <td className="whitespace-nowrap px-4 py-3 font-medium text-slate-900">
                  {MODEL_LABEL[l.model] ?? l.model}
                </td>
                <td className="max-w-md px-4 py-3">
                  <span className="line-clamp-1 text-slate-700">{l.trim || l.title}</span>
                </td>
                <td className="whitespace-nowrap px-4 py-3 font-semibold text-slate-900">
                  {formatPrice(l.price_eur)}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-600">{formatKm(l.mileage_km)}</td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-600">{formatYear(l.year)}</td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                  {l.power_kw != null ? `${l.power_kw} kW` : "—"}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                  {CONDITION_LABEL[l.condition] ?? l.condition}
                </td>
                <td className="max-w-[12rem] px-4 py-3 text-slate-600">
                  <span className="line-clamp-1">{l.location ?? "—"}</span>
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-500">
                  {SOURCE_LABEL[l.source] ?? l.source}
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <select
                    aria-label={`Tag for ${l.trim || l.title}`}
                    value={l.tag ?? ""}
                    onChange={(e) => onTagChange(l.id, e.target.value || null)}
                    className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-700"
                  >
                    {TAG_OPTIONS.map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <a
                    href={l.url}
                    target="_blank"
                    rel="noreferrer"
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

interface SortableHeaderProps {
  label: string;
  field: SortField;
  sort: SortState | null;
  onSort: (field: SortField) => void;
}

function SortableHeader({ label, field, sort, onSort }: SortableHeaderProps) {
  const active = sort?.field === field;
  const arrow = active ? (sort?.direction === "asc" ? " ▲" : " ▼") : "";
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
