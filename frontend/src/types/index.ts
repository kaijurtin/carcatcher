export interface AiEvaluation {
  summary: string;
  pros?: string[];
  cons?: string[];
  red_flags?: string[];
  deal_verdict: "good" | "fair" | "overpriced";
  confidence: "low" | "medium" | "high";
}

export interface Listing {
  id: number;
  source: string;
  source_id: string;
  url: string;
  status: string;
  raw_title: string;
  raw_price: string | null;
  location_raw: string | null;
  images: string[];
  price: number | null;
  price_negotiable: boolean;
  mileage_km: number | null;
  year: number | null;
  make: string | null;
  model: string | null;
  variant: string | null;
  fuel: string | null;
  transmission: string | null;
  power_kw: number | null;
  body_type: string | null;
  location_city: string | null;
  location_plz: string | null;
  seller_type: string | null;
  fair_price_estimate: number | null;
  deal_score: number | null;
  comp_count: number | null;
  ai_evaluation: AiEvaluation | null;
  ai_evaluated_at: string | null;
  first_seen_at: string;
  last_seen_at: string;
  scraped_at: string;
}

export interface ListingsPage {
  items: Listing[];
  total: number;
  page: number;
  page_size: number;
}

export interface CrawlRun {
  id: number;
  source: string;
  trigger: string;
  status: "running" | "done" | "failed";
  started_at: string;
  finished_at: string | null;
  listings_seen: number;
  listings_new: number;
  listings_updated: number;
  listings_gone: number;
  haiku_calls: number;
  sonnet_calls: number;
  opus_calls: number;
  est_cost_usd: number;
  error: string | null;
}

export interface StructuredFilters {
  make?: string | null;
  model?: string | null;
  variant?: string | null;
  year_min?: number | null;
  year_max?: number | null;
  price_min?: number | null;
  price_max?: number | null;
  mileage_max?: number | null;
  fuel?: string | null;
  transmission?: string | null;
  seller_type?: string | null;
  plz?: string | null;
  keywords?: string | null;
}

export interface SavedSearch {
  id: number;
  name: string;
  criteria: StructuredFilters;
  nl_query: string | null;
  auto_evaluate: boolean;
  created_at: string;
  updated_at: string;
}

export interface SavedSearchCreate {
  name: string;
  criteria: StructuredFilters;
  nl_query?: string | null;
  auto_evaluate?: boolean;
}

export interface NlSearchResponse {
  query: string;
  filters: Record<string, unknown>;
  ranking: { field: string; direction: string }[];
  rationale: string;
  results: Listing[];
  total: number;
}

export interface Recommendation {
  top_pick_id: number;
  summary: string;
  ranking: { listing_id: number; rank: number; reason: string }[];
  caveats: string[];
}

export interface RecommendResponse {
  recommendation: Recommendation;
  listings: Listing[];
}

export type SortField = "scraped_at" | "price" | "deal_score" | "year" | "mileage_km";

export interface ListingQuery {
  source?: string;
  make?: string;
  model?: string;
  price_max?: number;
  mileage_max?: number;
  year_min?: number;
  sort?: SortField;
  order?: "asc" | "desc";
  page?: number;
  page_size?: number;
}
