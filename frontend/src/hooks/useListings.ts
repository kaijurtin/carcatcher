import { useCallback, useEffect, useState } from "react";
import { getListings } from "../api/client";
import type { ListingQuery, ListingsPage } from "../types";

interface State {
  data: ListingsPage | null;
  loading: boolean;
  error: string | null;
}

export function useListings(query: ListingQuery) {
  const [state, setState] = useState<State>({
    data: null,
    loading: true,
    error: null,
  });

  // Serialize the query so the effect re-runs only on real changes.
  const key = JSON.stringify(query);

  const reload = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }));
    getListings(query)
      .then((data) => setState({ data, loading: false, error: null }))
      .catch((e: unknown) =>
        setState({
          data: null,
          loading: false,
          error: e instanceof Error ? e.message : "Failed to load listings",
        }),
      );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { ...state, reload };
}
