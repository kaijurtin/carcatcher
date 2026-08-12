const EUR = new Intl.NumberFormat("de-DE", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});
const NUM = new Intl.NumberFormat("de-DE");
const KWH = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 1 });
const KM_DISTANCE = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });

export function formatPrice(value: number | null): string {
  return value != null ? EUR.format(value) : "—";
}

export function formatKm(value: number | null): string {
  return value != null ? `${NUM.format(value)} km` : "—";
}

export function formatYear(value: number | null): string {
  return value != null ? String(value) : "—";
}

export function formatBatteryKwh(value: number | null): string {
  return value != null ? `${KWH.format(value)} kWh` : "—";
}

export function formatDistanceKm(value: number | null): string {
  return value != null ? `${KM_DISTANCE.format(value)} km` : "—";
}
