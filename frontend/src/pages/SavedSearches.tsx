import { useCallback, useEffect, useState } from "react";
import {
  deleteSavedSearch,
  duplicateSavedSearch,
  getSavedSearches,
  runSavedSearch,
  updateSavedSearch,
} from "../api/client";
import { createSavedSearchFromQuery, filtersForQuery } from "../lib/savedSearch";
import type { SavedSearch, StructuredFilters } from "../types";

function criteriaSummary(s: SavedSearch): string {
  if (s.nl_query) return s.nl_query;
  const c: StructuredFilters = s.criteria;
  const parts = [
    [c.make, c.model].filter(Boolean).join(" "),
    c.year_min ? `from ${c.year_min}` : "",
    c.price_max ? `≤ €${c.price_max.toLocaleString("de-DE")}` : "",
    c.mileage_max ? `≤ ${c.mileage_max.toLocaleString("de-DE")} km` : "",
    c.battery_kwh_min ? `≥ ${c.battery_kwh_min} kWh` : "",
  ].filter(Boolean);
  return parts.join(" · ") || "any car";
}

export function SavedSearches() {
  const [searches, setSearches] = useState<SavedSearch[]>([]);
  const [query, setQuery] = useState("");
  const [name, setName] = useState("");
  const [autoEvaluate, setAutoEvaluate] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [running, setRunning] = useState<Set<number>>(new Set());

  const load = useCallback(async () => {
    try {
      setSearches(await getSavedSearches());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || !name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await createSavedSearchFromQuery(name.trim(), query.trim(), autoEvaluate);
      setQuery("");
      setName("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
    } finally {
      setBusy(false);
    }
  };

  const toggleAuto = async (s: SavedSearch) => {
    await updateSavedSearch(s.id, { auto_evaluate: !s.auto_evaluate });
    await load();
  };

  const toggleEnabled = async (s: SavedSearch) => {
    await updateSavedSearch(s.id, { enabled: !s.enabled });
    await load();
  };

  const runNow = async (s: SavedSearch) => {
    setError(null);
    const result = await runSavedSearch(s.id);
    if (result === "running") {
      setError("A crawl is already running — try again shortly.");
      return;
    }
    if (result === "error") {
      setError("Could not start the run.");
      return;
    }
    setRunning((prev) => new Set(prev).add(s.id));
    setTimeout(() => {
      setRunning((prev) => {
        const next = new Set(prev);
        next.delete(s.id);
        return next;
      });
      load();
    }, 8000);
  };

  const rename = async (s: SavedSearch) => {
    const next = window.prompt("Rename saved search:", s.name)?.trim();
    if (!next || next === s.name) return;
    setError(null);
    try {
      await updateSavedSearch(s.id, { name: next });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Rename failed");
    }
  };

  const duplicate = async (s: SavedSearch) => {
    setError(null);
    try {
      await duplicateSavedSearch(s.id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Duplicate failed");
    }
  };

  const editQuery = async (s: SavedSearch) => {
    const next = window.prompt("Edit the search query:", s.nl_query ?? "")?.trim();
    if (!next || next === s.nl_query) return;
    setError(null);
    try {
      const criteria = await filtersForQuery(next);
      await updateSavedSearch(s.id, { nl_query: next, criteria });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Update failed");
    }
  };

  const remove = async (s: SavedSearch) => {
    if (!window.confirm(`Delete "${s.name}" and its results?`)) return;
    await deleteSavedSearch(s.id);
    await load();
  };

  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-slate-800">Saved searches</h2>
        <p className="text-sm text-slate-500">
          Describe the car you want in plain language — the AI turns it into a focused
          background crawl. Turn on <em>auto-evaluate</em> to always run the AI verdict on
          matches.
        </p>
      </div>

      <form
        onSubmit={submit}
        className="space-y-3 rounded-lg border border-slate-200 bg-white p-4"
      >
        <label className="flex flex-col gap-1 text-xs text-slate-500">
          Search query
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="VW ID.4 GTX, ab 2022, mindestens 77 kWh, SoH ≥ 90%"
            className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-800 focus:border-sky-400 focus:outline-none"
          />
        </label>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-1 flex-col gap-1 text-xs text-slate-500">
            Name *
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="ID.4 long-range deals"
              className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-800 focus:border-sky-400 focus:outline-none"
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={autoEvaluate}
              onChange={(e) => setAutoEvaluate(e.target.checked)}
              className="h-4 w-4 accent-violet-600"
            />
            Auto-evaluate
          </label>
          <button
            type="submit"
            disabled={busy || !query.trim() || !name.trim()}
            className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:bg-slate-300"
          >
            {busy ? "Saving…" : "Add search"}
          </button>
        </div>
      </form>

      {error && <div className="text-sm text-rose-600">{error}</div>}

      {searches.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-slate-500">
          No saved searches yet. Describe a car above to start finding deals.
        </div>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
          {searches.map((s) => (
            <li key={s.id} className="flex items-center justify-between gap-4 px-4 py-3">
              <div className="min-w-0">
                <div className="font-medium text-slate-900">{s.name}</div>
                <div className="line-clamp-1 text-xs text-slate-400">{criteriaSummary(s)}</div>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <label className="flex items-center gap-1.5 text-xs text-slate-500">
                  <input
                    type="checkbox"
                    checked={s.enabled}
                    onChange={() => toggleEnabled(s)}
                    className="h-3.5 w-3.5 accent-sky-600"
                  />
                  scheduled
                </label>
                <label className="flex items-center gap-1.5 text-xs text-slate-500">
                  <input
                    type="checkbox"
                    checked={s.auto_evaluate}
                    onChange={() => toggleAuto(s)}
                    className="h-3.5 w-3.5 accent-violet-600"
                  />
                  auto-eval
                </label>
                <button
                  onClick={() => runNow(s)}
                  disabled={running.has(s.id)}
                  className="rounded-md bg-sky-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-sky-700 disabled:bg-slate-300"
                >
                  {running.has(s.id) ? "Running…" : "Run now"}
                </button>
                <button
                  onClick={() => editQuery(s)}
                  className="text-xs font-medium text-slate-500 hover:text-slate-800"
                >
                  Edit
                </button>
                <button
                  onClick={() => rename(s)}
                  className="text-xs font-medium text-slate-500 hover:text-slate-800"
                >
                  Rename
                </button>
                <button
                  onClick={() => duplicate(s)}
                  className="text-xs font-medium text-slate-500 hover:text-slate-800"
                >
                  Duplicate
                </button>
                <button
                  onClick={() => remove(s)}
                  className="text-xs font-medium text-rose-600 hover:text-rose-700"
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
