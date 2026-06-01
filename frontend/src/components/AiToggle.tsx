import { useCallback, useEffect, useState } from "react";
import { getSettings, setAiEnabled } from "../api/client";

/**
 * Dashboard switch for AI normalization/evaluation. When off, crawls spend zero
 * tokens — listings are still categorized and sorted by the deterministic rules.
 * Disabled (with a hint) when the server has no Anthropic key configured.
 */
export function AiToggle() {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [configured, setConfigured] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getSettings()
      .then((s) => {
        setEnabled(s.ai_enabled);
        setConfigured(s.ai_configured);
      })
      .catch(() => setEnabled(null));
  }, []);

  const onToggle = useCallback(async () => {
    if (enabled === null || busy) return;
    const next = !enabled;
    setEnabled(next); // optimistic
    setBusy(true);
    try {
      const s = await setAiEnabled(next);
      setEnabled(s.ai_enabled);
      setConfigured(s.ai_configured);
    } catch {
      setEnabled(!next); // revert on failure
    } finally {
      setBusy(false);
    }
  }, [enabled, busy]);

  if (enabled === null) return null;

  const isOn = enabled && configured;
  const title = configured
    ? isOn
      ? "AI on — listings are normalized by Claude (spends tokens)"
      : "AI off — crawl + categorize + sort only, no tokens spent"
    : "No Anthropic key configured on the server";

  return (
    <label
      className={`flex items-center gap-2 text-sm ${configured ? "text-slate-600" : "text-slate-400"}`}
      title={title}
    >
      <span>AI</span>
      <button
        type="button"
        role="switch"
        aria-checked={isOn}
        aria-label="Toggle AI normalization"
        onClick={onToggle}
        disabled={busy || !configured}
        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors disabled:opacity-50 ${
          isOn ? "bg-sky-600" : "bg-slate-300"
        }`}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
            isOn ? "translate-x-4" : "translate-x-1"
          }`}
        />
      </button>
    </label>
  );
}
