const EUR = new Intl.NumberFormat("de-DE", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});
const NUM = new Intl.NumberFormat("de-DE");

export function formatPrice(value: number | null): string {
  return value != null ? EUR.format(value) : "—";
}

export function formatKm(value: number | null): string {
  return value != null ? `${NUM.format(value)} km` : "—";
}

export function formatYear(value: number | null): string {
  return value != null ? String(value) : "—";
}
