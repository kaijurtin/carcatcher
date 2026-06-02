import type { ListingQuery } from "../types";

export interface ListingFilterValues {
  price_min?: number;
  price_max?: number;
  year_min?: number;
  mileage_max?: number;
  battery_kwh_min?: number;
  battery_kwh_max?: number;
  battery_soh_min?: number;
  seller_type?: string;
}

interface ListingFiltersProps {
  value: ListingFilterValues;
  onChange: (next: ListingFilterValues) => void;
}

const num = (v: string): number | undefined =>
  v.trim() === "" ? undefined : Number(v);

const SELLER_TYPES: { value: string; label: string }[] = [
  { value: "", label: "Any seller" },
  { value: "private", label: "Private" },
  { value: "dealer", label: "Dealer" },
];

/** Compact filter bar for numeric ranges + seller type. Applies on change. */
export function ListingFilters({ value, onChange }: ListingFiltersProps) {
  const set = (patch: Partial<ListingFilterValues>) => onChange({ ...value, ...patch });
  const hasFilters =
    value.price_min !== undefined ||
    value.price_max !== undefined ||
    value.year_min !== undefined ||
    value.mileage_max !== undefined ||
    value.battery_kwh_min !== undefined ||
    value.battery_kwh_max !== undefined ||
    value.battery_soh_min !== undefined ||
    (value.seller_type ?? "") !== "";

  return (
    <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
        Filter
      </span>

      <NumberRange
        label="Price (€)"
        min={value.price_min}
        max={value.price_max}
        onMin={(v) => set({ price_min: v })}
        onMax={(v) => set({ price_max: v })}
      />

      <label className="flex flex-col gap-1 text-xs text-slate-500">
        Year (min)
        <input
          type="number"
          inputMode="numeric"
          aria-label="Year min"
          value={value.year_min ?? ""}
          onChange={(e) => set({ year_min: num(e.target.value) })}
          className="w-20 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-700"
        />
      </label>

      <label className="flex flex-col gap-1 text-xs text-slate-500">
        Mileage (max km)
        <input
          type="number"
          inputMode="numeric"
          aria-label="Mileage max"
          value={value.mileage_max ?? ""}
          onChange={(e) => set({ mileage_max: num(e.target.value) })}
          className="w-24 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-700"
        />
      </label>

      <NumberRange
        label="Battery (kWh)"
        min={value.battery_kwh_min}
        max={value.battery_kwh_max}
        onMin={(v) => set({ battery_kwh_min: v })}
        onMax={(v) => set({ battery_kwh_max: v })}
      />

      <label className="flex flex-col gap-1 text-xs text-slate-500">
        SoH (min %)
        <input
          type="number"
          inputMode="numeric"
          aria-label="Battery SoH min"
          value={value.battery_soh_min ?? ""}
          onChange={(e) => set({ battery_soh_min: num(e.target.value) })}
          className="w-20 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-700"
        />
      </label>

      <label className="flex flex-col gap-1 text-xs text-slate-500">
        Seller
        <select
          aria-label="Seller type"
          value={value.seller_type ?? ""}
          onChange={(e) => set({ seller_type: e.target.value || undefined })}
          className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-700"
        >
          {SELLER_TYPES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </label>

      {hasFilters && (
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

function NumberRange({
  label,
  min,
  max,
  onMin,
  onMax,
}: {
  label: string;
  min?: number;
  max?: number;
  onMin: (v: number | undefined) => void;
  onMax: (v: number | undefined) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-slate-500">
      {label}
      <span className="flex items-center gap-1">
        <input
          type="number"
          inputMode="numeric"
          aria-label={`${label} min`}
          value={min ?? ""}
          onChange={(e) => onMin(num(e.target.value))}
          className="w-20 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-700"
        />
        <span className="text-slate-400">–</span>
        <input
          type="number"
          inputMode="numeric"
          aria-label={`${label} max`}
          value={max ?? ""}
          onChange={(e) => onMax(num(e.target.value))}
          className="w-20 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-700"
        />
      </span>
    </label>
  );
}

/** Map filter values into a ListingQuery, omitting empties. */
export function toListingQuery(v: ListingFilterValues): Partial<ListingQuery> {
  return {
    price_min: v.price_min,
    price_max: v.price_max,
    year_min: v.year_min,
    mileage_max: v.mileage_max,
    battery_kwh_min: v.battery_kwh_min,
    battery_kwh_max: v.battery_kwh_max,
    battery_soh_min: v.battery_soh_min,
    seller_type: v.seller_type || undefined,
  };
}
