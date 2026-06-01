import type { Listing } from "../types";
import { formatKm, formatKmPerYear, formatPrice, formatYear } from "../lib/format";
import { DealScoreBadge } from "./DealScoreBadge";

export const SOURCE_LABEL: Record<string, string> = {
  kleinanzeigen: "Kleinanzeigen",
  autoscout24: "AutoScout24",
  mobilede: "mobile.de",
};

const FUEL_LABEL: Record<string, string> = {
  petrol: "Benzin",
  diesel: "Diesel",
  hybrid: "Hybrid",
  electric: "Elektro",
  lpg: "LPG",
  cng: "CNG",
};

function specsLine(l: Listing): string {
  const parts = [
    l.variant,
    l.fuel ? (FUEL_LABEL[l.fuel] ?? l.fuel) : null,
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

interface ListingsTableProps {
  items: Listing[];
  onSelect?: (id: number) => void;
  selectedIds?: Set<number>;
  onToggleSelect?: (id: number) => void;
  favoriteIds?: Set<number>;
  onToggleFavorite?: (id: number) => void;
}

export function ListingsTable({
  items,
  onSelect,
  selectedIds,
  onToggleSelect,
  favoriteIds,
  onToggleFavorite,
}: ListingsTableProps) {
  const selectable = !!onToggleSelect;
  const favoritable = !!onToggleFavorite;
  if (items.length === 0) {
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
            {favoritable && <th className="w-8 px-2 py-3" />}
            {selectable && <th className="w-10 px-4 py-3" />}
            <th className="px-4 py-3 font-medium">Model</th>
            <th className="px-4 py-3 font-medium">Price</th>
            <th className="px-4 py-3 font-medium">Deal</th>
            <th className="px-4 py-3 font-medium">Year</th>
            <th className="px-4 py-3 font-medium">Mileage</th>
            <th className="px-4 py-3 font-medium">km/Jahr</th>
            <th className="px-4 py-3 font-medium">Battery</th>
            <th className="px-4 py-3 font-medium">SoH</th>
            <th className="px-4 py-3 font-medium">Location</th>
            <th className="px-4 py-3 font-medium" />
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.map((l) => (
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
              <td className="max-w-md px-4 py-3">
                <span className="flex items-center gap-2">
                  <span className="line-clamp-1 font-medium text-slate-900">
                    {modelLine(l)}
                  </span>
                  <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">
                    {SOURCE_LABEL[l.source] ?? l.source}
                  </span>
                </span>
                {l.make && specsLine(l) && (
                  <span className="line-clamp-1 text-xs text-slate-400">
                    {specsLine(l)}
                  </span>
                )}
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
              <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                {formatYear(l.year)}
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                {formatKm(l.mileage_km)}
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                {formatKmPerYear(l.mileage_km, l.year)}
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                {l.battery_kwh ? `${l.battery_kwh} kWh` : "—"}
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
          ))}
        </tbody>
      </table>
    </div>
  );
}
