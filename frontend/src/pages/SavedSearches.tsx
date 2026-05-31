import { useCallback, useEffect, useState } from "react";
import {
  createSavedSearch,
  deleteSavedSearch,
  getSavedSearches,
  updateSavedSearch,
} from "../api/client";
import type { SavedSearch, StructuredFilters } from "../types";

const EMPTY = {
  name: "",
  make: "",
  model: "",
  price_max: "",
  year_min: "",
  mileage_max: "",
  auto_evaluate: true,
};

function criteriaSummary(c: StructuredFilters): string {
  const parts = [
    [c.make, c.model].filter(Boolean).join(" "),
    c.year_min ? `from ${c.year_min}` : "",
    c.price_max ? `≤ €${c.price_max.toLocaleString("de-DE")}` : "",
    c.mileage_max ? `≤ ${c.mileage_max.toLocaleString("de-DE")} km` : "",
  ].filter(Boolean);
  return parts.join(" · ") || "any car";
}

export function SavedSearches() {
  const [searches, setSearches] = useState<SavedSearch[]>([]);
  const [form, setForm] = useState({ ...EMPTY });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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

  const num = (v: string): number | undefined =>
    v.trim() === "" ? undefined : Number(v);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const criteria: StructuredFilters = {
        make: form.make.trim() || undefined,
        model: form.model.trim() || undefined,
        price_max: num(form.price_max),
        year_min: num(form.year_min),
        mileage_max: num(form.mileage_max),
      };
      await createSavedSearch({
        name: form.name.trim(),
        criteria,
        auto_evaluate: form.auto_evaluate,
      });
      setForm({ ...EMPTY });
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

  const remove = async (id: number) => {
    await deleteSavedSearch(id);
    await load();
  };

  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-slate-800">Saved searches</h2>
        <p className="text-sm text-slate-500">
          Focused searches drive the background crawl — and give deal scoring enough
          comparable cars to work. Turn on <em>auto-evaluate</em> to always run the AI
          verdict on matches.
        </p>
      </div>

      <form
        onSubmit={submit}
        className="grid grid-cols-2 gap-3 rounded-lg border border-slate-200 bg-white p-4 sm:grid-cols-3"
      >
        <Field label="Name *" value={form.name} onChange={(v) => setForm({ ...form, name: v })} placeholder="VW Golf budget" />
        <Field label="Make" value={form.make} onChange={(v) => setForm({ ...form, make: v })} placeholder="Volkswagen" />
        <Field label="Model" value={form.model} onChange={(v) => setForm({ ...form, model: v })} placeholder="Golf" />
        <Field label="Max price (€)" value={form.price_max} onChange={(v) => setForm({ ...form, price_max: v })} placeholder="15000" type="number" />
        <Field label="Min year" value={form.year_min} onChange={(v) => setForm({ ...form, year_min: v })} placeholder="2016" type="number" />
        <Field label="Max km" value={form.mileage_max} onChange={(v) => setForm({ ...form, mileage_max: v })} placeholder="100000" type="number" />
        <label className="col-span-2 flex items-center gap-2 text-sm text-slate-600 sm:col-span-2">
          <input
            type="checkbox"
            checked={form.auto_evaluate}
            onChange={(e) => setForm({ ...form, auto_evaluate: e.target.checked })}
            className="h-4 w-4 accent-violet-600"
          />
          Auto-evaluate matches with AI
        </label>
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:bg-slate-300"
        >
          {busy ? "Saving…" : "Add search"}
        </button>
      </form>

      {error && <div className="text-sm text-rose-600">{error}</div>}

      {searches.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-slate-500">
          No saved searches yet. Add one above to start finding deals on the cars you want.
        </div>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
          {searches.map((s) => (
            <li key={s.id} className="flex items-center justify-between px-4 py-3">
              <div>
                <div className="font-medium text-slate-900">{s.name}</div>
                <div className="text-xs text-slate-400">{criteriaSummary(s.criteria)}</div>
              </div>
              <div className="flex items-center gap-4">
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
                  onClick={() => remove(s.id)}
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

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-slate-500">
      {label}
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800 focus:border-sky-400 focus:outline-none"
      />
    </label>
  );
}
