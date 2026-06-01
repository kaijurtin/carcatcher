/** Shared helpers for turning a natural-language query into a saved search.
 *  Used by both the Dashboard ("Save this search") and the Saved Searches page. */

import { createSavedSearch, nlSearch } from "../api/client";
import type { SavedSearch, StructuredFilters } from "../types";

/** Translate a free-text query into structured filters via the NL endpoint. */
export async function filtersForQuery(query: string): Promise<StructuredFilters> {
  const nl = await nlSearch(query);
  return nl.filters as StructuredFilters;
}

/** Create a saved search from a free-text query (stores both nl_query and the
 *  derived criteria — criteria drives the crawl and the make/model match filter). */
export async function createSavedSearchFromQuery(
  name: string,
  query: string,
  autoEvaluate: boolean,
): Promise<SavedSearch> {
  return createSavedSearch({
    name,
    criteria: await filtersForQuery(query),
    nl_query: query,
    auto_evaluate: autoEvaluate,
  });
}
