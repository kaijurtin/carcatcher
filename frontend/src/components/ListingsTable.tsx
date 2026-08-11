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

export interface TableFilters {
  model?: string;
  source?: string;
  max_price?: number;
  max_km?: number;
  trim?: string;
}

const num = (v: string): number | undefined => (v.trim() === "" ? undefined : Number(v));

interface ListingsTableProps {
  items: Listing[];
  filters: TableFilters;
  onFilterChange: (next: TableFilters) => void;
}

export function ListingsTable({ items, filters, onFilterChange }: ListingsTableProps) {
  const f = filters;
  const set = (patch: Partial<TableFilters>) => onFilterChange({ ...f, ...patch });

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-3 font-medium">Model</th>
            <th className="px-4 py-3 font-medium">Trim</th>
            <th className="px-4 py-3 font-medium">Price</th>
            <th className="px-4 py-3 font-medium">KM</th>
            <th className="px-4 py-3 font-medium">Year</th>
            <th className="px-4 py-3 font-medium">Power</th>
            <th className="px-4 py-3 font-medium">Condition</th>
            <th className="px-4 py-3 font-medium">Location</th>
            <th className="px-4 py-3 font-medium">Source</th>
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
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.length === 0 ? (
            <tr>
              <td colSpan={10} className="px-4 py-12 text-center text-slate-500">
                No listings match these filters.
              </td>
            </tr>
          ) : (
            items.map((l) => (
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
                  {l.condition === "new" ? "Neu" : "Gebraucht"}
                </td>
                <td className="max-w-[12rem] px-4 py-3 text-slate-600">
                  <span className="line-clamp-1">{l.location ?? "—"}</span>
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-500">
                  {SOURCE_LABEL[l.source] ?? l.source}
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
