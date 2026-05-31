import type { Listing } from "../types";
import { formatKm, formatPrice, formatYear } from "../lib/format";

export function ListingsTable({ items }: { items: Listing[] }) {
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
            <th className="px-4 py-3 font-medium">Title</th>
            <th className="px-4 py-3 font-medium">Price</th>
            <th className="px-4 py-3 font-medium">Year</th>
            <th className="px-4 py-3 font-medium">Mileage</th>
            <th className="px-4 py-3 font-medium">Location</th>
            <th className="px-4 py-3 font-medium" />
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.map((l) => (
            <tr key={l.id} className="hover:bg-slate-50">
              <td className="max-w-md px-4 py-3">
                <span className="line-clamp-1 font-medium text-slate-900">
                  {l.make && l.model ? `${l.make} ${l.model}` : l.raw_title}
                </span>
                {l.make && (
                  <span className="line-clamp-1 text-xs text-slate-400">
                    {l.raw_title}
                  </span>
                )}
              </td>
              <td className="whitespace-nowrap px-4 py-3 font-semibold text-slate-900">
                {formatPrice(l.price, l.raw_price)}
                {l.price_negotiable && (
                  <span className="ml-1 text-xs font-normal text-slate-400">VB</span>
                )}
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                {formatYear(l.year)}
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                {formatKm(l.mileage_km)}
              </td>
              <td className="max-w-[12rem] px-4 py-3 text-slate-600">
                <span className="line-clamp-1">{l.location_raw ?? "—"}</span>
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
          ))}
        </tbody>
      </table>
    </div>
  );
}
