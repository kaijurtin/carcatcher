import { useEffect, useState } from "react";
import { getFacets } from "../api/client";
import type { Facets } from "../types";

export interface FacetSelection {
  model?: string;
  variant?: string;
  battery_kwh_min?: number;
  battery_kwh_max?: number;
}

interface FacetFiltersProps {
  scope: { search_id?: number; source?: string };
  value: FacetSelection;
  onChange: (next: FacetSelection) => void;
}

/** Refine-by panel: distinct models/variants (with counts) and a battery-kWh range
 *  present in the current result scope. Cascades — selecting a model re-narrows the
 *  variant list and battery range. */
export function FacetFilters({ scope, value, onChange }: FacetFiltersProps) {
  const [facets, setFacets] = useState<Facets | null>(null);
  const key = JSON.stringify({ scope, value });

  useEffect(() => {
    let cancelled = false;
    getFacets({ ...scope, ...value })
      .then((f) => !cancelled && setFacets(f))
      .catch(() => !cancelled && setFacets(null));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const hasModels = (facets?.models?.length ?? 0) > 0;
  const hasVariants = (facets?.variants?.length ?? 0) > 0;
  const hasBattery = facets?.battery_kwh != null;
  if (!facets || (!hasModels && !hasVariants && !hasBattery)) return null;

  const num = (v: string): number | undefined =>
    v.trim() === "" ? undefined : Number(v);

  return (
    <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
        Refine
      </span>

      {hasModels && (
        <label className="flex flex-col gap-1 text-xs text-slate-500">
          Model
          <select
            value={value.model ?? ""}
            onChange={(e) =>
              onChange({ ...value, model: e.target.value || undefined, variant: undefined })
            }
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-700"
          >
            <option value="">All models</option>
            {facets.models.map((m) => (
              <option key={m.value} value={m.value}>
                {m.value} ({m.count})
              </option>
            ))}
          </select>
        </label>
      )}

      {hasVariants && (
        <label className="flex flex-col gap-1 text-xs text-slate-500">
          Variant
          <select
            value={value.variant ?? ""}
            onChange={(e) => onChange({ ...value, variant: e.target.value || undefined })}
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-700"
          >
            <option value="">All variants</option>
            {facets.variants.map((v) => (
              <option key={v.value} value={v.value}>
                {v.value} ({v.count})
              </option>
            ))}
          </select>
        </label>
      )}

      {hasBattery && (
        <label className="flex flex-col gap-1 text-xs text-slate-500">
          Battery (kWh)
          <span className="flex items-center gap-1">
            <input
              type="number"
              inputMode="numeric"
              value={value.battery_kwh_min ?? ""}
              placeholder={String(facets.battery_kwh!.min)}
              onChange={(e) => onChange({ ...value, battery_kwh_min: num(e.target.value) })}
              className="w-20 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-700"
            />
            <span className="text-slate-400">–</span>
            <input
              type="number"
              inputMode="numeric"
              value={value.battery_kwh_max ?? ""}
              placeholder={String(facets.battery_kwh!.max)}
              onChange={(e) => onChange({ ...value, battery_kwh_max: num(e.target.value) })}
              className="w-20 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-700"
            />
          </span>
        </label>
      )}

      {(value.model || value.variant || value.battery_kwh_min || value.battery_kwh_max) && (
        <button
          onClick={() => onChange({})}
          className="text-xs font-medium text-slate-500 hover:text-slate-700"
        >
          Clear
        </button>
      )}
    </div>
  );
}
