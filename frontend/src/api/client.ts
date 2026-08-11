/** Thin fetch wrapper around the CarCatcher API. */

import type { Listing, ListingQuery, RefreshSummary } from "../types";

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

export function getListings(query: ListingQuery = {}): Promise<Listing[]> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const qs = params.toString();
  return apiGet<Listing[]>(`/listings${qs ? `?${qs}` : ""}`);
}

export async function refresh(): Promise<RefreshSummary> {
  const resp = await fetch(`${BASE}/refresh`, { method: "POST" });
  if (!resp.ok) {
    throw new ApiError(resp.status, `refresh failed: ${resp.status}`);
  }
  return (await resp.json()) as RefreshSummary;
}
