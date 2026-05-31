import type { CrawlRun } from "../types";

const STYLES: Record<CrawlRun["status"], string> = {
  running: "bg-amber-100 text-amber-700",
  done: "bg-emerald-100 text-emerald-700",
  failed: "bg-rose-100 text-rose-700",
};

export function RunStatusPill({ run }: { run: CrawlRun | null }) {
  if (!run) {
    return <span className="text-xs text-slate-400">No crawls yet</span>;
  }
  const cost = run.est_cost_usd ? ` · $${run.est_cost_usd.toFixed(2)}` : "";
  const detail =
    run.status === "running"
      ? "crawling…"
      : run.status === "failed"
        ? "failed"
        : `${run.listings_new} new · ${run.listings_seen} seen${cost}`;
  return (
    <span className="flex items-center gap-2 text-xs text-slate-500">
      <span className={`rounded-full px-2 py-0.5 font-medium ${STYLES[run.status]}`}>
        {run.status}
      </span>
      {detail}
    </span>
  );
}
