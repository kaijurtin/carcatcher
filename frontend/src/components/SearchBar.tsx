import { useState } from "react";

export function SearchBar({
  onSearch,
  onClear,
  loading,
  active,
}: {
  onSearch: (query: string) => void;
  onClear: () => void;
  loading: boolean;
  active: boolean;
}) {
  const [value, setValue] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const q = value.trim();
    if (q) onSearch(q);
  };

  return (
    <form onSubmit={submit} className="flex items-center gap-2">
      <div className="relative flex-1">
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Ask in plain language — e.g. 'sparsamer Kombi unter 12.000, Automatik'"
          className="w-full rounded-lg border border-slate-300 bg-white px-4 py-2 pr-10 text-sm text-slate-800 placeholder:text-slate-400 focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-400"
        />
        <span className="pointer-events-none absolute right-3 top-2.5 text-slate-300">
          ⌕
        </span>
      </div>
      <button
        type="submit"
        disabled={loading}
        className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:bg-slate-300"
      >
        {loading ? "Searching…" : "Search"}
      </button>
      {active && (
        <button
          type="button"
          onClick={() => {
            setValue("");
            onClear();
          }}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
        >
          Clear
        </button>
      )}
    </form>
  );
}
