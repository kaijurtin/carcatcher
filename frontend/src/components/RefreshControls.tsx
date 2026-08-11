import { useState } from "react";
import { refresh } from "../api/client";
import type { RefreshSummary } from "../types";

export function RefreshControls({ onComplete }: { onComplete?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState<RefreshSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const onClick = async () => {
    setBusy(true);
    setError(null);
    setSummary(null);
    try {
      const result = await refresh();
      setSummary(result);
      onComplete?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Refresh failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-3">
      {summary && (
        <span className="text-xs text-slate-500">
          Updated {new Date(summary.refreshed_at).toLocaleTimeString("de-DE")} — +{summary.added}{" "}
          new, {summary.updated} updated, {summary.gone} gone
          {summary.failed_sources.length > 0 && (
            <span className="text-rose-600"> ({summary.failed_sources.join(", ")} failed)</span>
          )}
        </span>
      )}
      <button
        onClick={onClick}
        disabled={busy}
        className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        {busy ? "Updating…" : "Update search"}
      </button>
      {error && <span className="text-xs text-rose-600">{error}</span>}
    </div>
  );
}
