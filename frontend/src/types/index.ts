export interface Listing {
  id: number;
  source: string;
  source_id: string;
  url: string;
  model: string;
  trim: string;
  price_eur: number | null;
  mileage_km: number | null;
  year: number | null;
  power_kw: number | null;
  battery_kwh: number | null;
  condition: string;
  location: string | null;
  distance_km: number | null;
  title: string;
  tag: string | null;
  status: string;
  first_seen_at: string;
  last_seen_at: string;
}

export interface ListingQuery {
  model?: string;
  source?: string;
  max_price?: number;
  max_km?: number;
  trim?: string;
}

export interface RefreshSummary {
  added: number;
  updated: number;
  gone: number;
  failed_sources: string[];
  refreshed_at: string;
}
