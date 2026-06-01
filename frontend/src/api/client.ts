/** Thin fetch wrapper around the CarCatcher API. */

import type {
  AppSettings,
  ListingsPage,
  ListingQuery,
  CrawlRun,
  Facets,
  Listing,
  NlSearchResponse,
  RecommendResponse,
  SavedSearch,
  SavedSearchCreate,
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

export function getFacets(query: ListingQuery = {}): Promise<Facets> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const qs = params.toString();
  return apiGet<Facets>(`/listings/facets${qs ? `?${qs}` : ""}`);
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

export async function setFavorite(id: number, favorite: boolean): Promise<void> {
  const resp = await fetch(`${BASE}/listings/${id}/favorite`, {
    method: favorite ? "PUT" : "DELETE",
  });
  if (!resp.ok && resp.status !== 204) {
    throw new ApiError(resp.status, `favorite update failed: ${resp.status}`);
  }
}

export function getRuns(limit = 10): Promise<CrawlRun[]> {
  return apiGet<CrawlRun[]>(`/runs?limit=${limit}`);
}

export function getSettings(): Promise<AppSettings> {
  return apiGet<AppSettings>("/settings");
}

export async function setAiEnabled(enabled: boolean): Promise<AppSettings> {
  const resp = await fetch(`${BASE}/settings/ai`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  if (!resp.ok) throw new ApiError(resp.status, `settings update failed: ${resp.status}`);
  return (await resp.json()) as AppSettings;
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

export function getSavedSearches(): Promise<SavedSearch[]> {
  return apiGet<SavedSearch[]>("/saved-searches");
}

export function createSavedSearch(body: SavedSearchCreate): Promise<SavedSearch> {
  return apiPost<SavedSearch>("/saved-searches", body);
}

export async function updateSavedSearch(
  id: number,
  body: Partial<SavedSearchCreate>,
): Promise<SavedSearch> {
  const resp = await fetch(`${BASE}/saved-searches/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new ApiError(resp.status, `update failed: ${resp.status}`);
  return (await resp.json()) as SavedSearch;
}

export function duplicateSavedSearch(id: number): Promise<SavedSearch> {
  return apiPost<SavedSearch>(`/saved-searches/${id}/duplicate`, {});
}

export async function deleteSavedSearch(id: number): Promise<void> {
  const resp = await fetch(`${BASE}/saved-searches/${id}`, { method: "DELETE" });
  if (!resp.ok && resp.status !== 204) {
    throw new ApiError(resp.status, `delete failed: ${resp.status}`);
  }
}

export async function runSavedSearch(id: number): Promise<RefreshResult> {
  const resp = await fetch(`${BASE}/saved-searches/${id}/run`, { method: "POST" });
  if (resp.status === 202) return "scheduled";
  if (resp.status === 409) return "running";
  return "error";
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
