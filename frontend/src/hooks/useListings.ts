import { useCallback, useEffect, useState } from "react";
import { getListings } from "../api/client";
import type { Listing, ListingQuery } from "../types";

interface State {
  data: Listing[] | null;
  loading: boolean;
  error: string | null;
}

export function useListings(query: ListingQuery) {
  const [state, setState] = useState<State>({
    data: null,
    loading: true,
    error: null,
  });

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
