/** Thin fetch wrapper around the CarCatcher API. */

import type {
  ListingsPage,
  ListingQuery,
  CrawlRun,
  Listing,
  NlSearchResponse,
  RecommendResponse,
} from "../types";

const BASE = "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`);
  if (!resp.ok) {
    throw new ApiError(resp.status, `GET ${path} failed: ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export interface HealthResponse {
  status: string;
}

export function getHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>("/health");
}

export function getListings(query: ListingQuery = {}): Promise<ListingsPage> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const qs = params.toString();
  return apiGet<ListingsPage>(`/listings${qs ? `?${qs}` : ""}`);
}

export function getListing(id: number): Promise<Listing> {
  return apiGet<Listing>(`/listings/${id}`);
}

export async function evaluateListing(id: number): Promise<Listing> {
  const resp = await fetch(`${BASE}/listings/${id}/evaluate`, { method: "POST" });
  if (resp.status === 409) {
    throw new ApiError(409, "AI is disabled or unconfigured on the server");
  }
  if (!resp.ok) {
    throw new ApiError(resp.status, `Evaluation failed: ${resp.status}`);
  }
  return (await resp.json()) as Listing;
}

export function getRuns(limit = 10): Promise<CrawlRun[]> {
  return apiGet<CrawlRun[]>(`/runs?limit=${limit}`);
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (resp.status === 409) {
    throw new ApiError(409, "AI is disabled or unconfigured on the server");
  }
  if (!resp.ok) {
    throw new ApiError(resp.status, `POST ${path} failed: ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export function nlSearch(query: string): Promise<NlSearchResponse> {
  return apiPost<NlSearchResponse>("/search/nl", { query });
}

export function recommend(listingIds: number[]): Promise<RecommendResponse> {
  return apiPost<RecommendResponse>("/recommend", { listing_ids: listingIds });
}

export type RefreshResult = "scheduled" | "running" | "unauthorized" | "error";

export async function triggerRefresh(secret: string): Promise<RefreshResult> {
  const resp = await fetch(`${BASE}/refresh`, {
    method: "POST",
    headers: { "X-Cron-Secret": secret },
  });
  if (resp.status === 202) return "scheduled";
  if (resp.status === 409) return "running";
  if (resp.status === 401) return "unauthorized";
  return "error";
}
