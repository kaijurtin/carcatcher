const EUR = new Intl.NumberFormat("de-DE", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});
const NUM = new Intl.NumberFormat("de-DE");

export function formatPrice(value: number | null, raw?: string | null): string {
  if (value != null) return EUR.format(value);
  return raw ?? "—";
}

export function formatKm(value: number | null): string {
  return value != null ? `${NUM.format(value)} km` : "—";
}

export function formatYear(value: number | null): string {
  return value != null ? String(value) : "—";
}

/** Annualized mileage: mileage_km ÷ age. "—" when mileage or year is unknown. */
export function formatKmPerYear(
  mileageKm: number | null,
  year: number | null,
  now: number = new Date().getFullYear(),
): string {
  if (mileageKm == null || year == null) return "—";
  const age = Math.max(1, now - year); // brand-new/future-reg cars: treat age as ≥1
  return `${NUM.format(Math.round(mileageKm / age))}/Jahr`;
}
