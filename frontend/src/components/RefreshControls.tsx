import { useCallback, useEffect, useRef, useState } from "react";
import { getRuns, triggerRefresh } from "../api/client";
import type { CrawlRun } from "../types";
import { clearSecret, ensureSecret } from "../lib/secret";
import { RunStatusPill } from "./RunStatusPill";

const POLL_MS = 3000;

export function RefreshControls({ onComplete }: { onComplete?: () => void }) {
  const [runs, setRuns] = useState<CrawlRun[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const latest = runs[0] ?? null;

  const loadRuns = useCallback(async () => {
    try {
      setRuns(await getRuns(5));
    } catch {
      /* ignore — pill simply shows last known state */
    }
  }, []);

  useEffect(() => {
    loadRuns();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [loadRuns]);

  const startPolling = useCallback(() => {
    setBusy(true);
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      let latestRuns: CrawlRun[] = [];
      try {
        latestRuns = await getRuns(5);
        setRuns(latestRuns);
      } catch {
        return;
      }
      if (!latestRuns[0] || latestRuns[0].status !== "running") {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
        setBusy(false);
        onComplete?.();
      }
    }, POLL_MS);
  }, [onComplete]);

  const onClick = async () => {
    const secret = ensureSecret();
    if (!secret) return;
    setMessage(null);
    setBusy(true);
    const result = await triggerRefresh(secret);
    if (result === "unauthorized") {
      clearSecret();
      setBusy(false);
      setMessage("Wrong secret — click again to re-enter.");
      return;
    }
    if (result === "error") {
      setBusy(false);
      setMessage("Refresh failed.");
      return;
    }
    startPolling(); // "scheduled" or "running"
  };

  return (
    <div className="flex items-center gap-3">
      <RunStatusPill run={latest} />
      <button
        onClick={onClick}
        disabled={busy}
        className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        {busy ? "Crawling…" : "Refresh"}
      </button>
      {message && <span className="text-xs text-rose-600">{message}</span>}
    </div>
  );
}
