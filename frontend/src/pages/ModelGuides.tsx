import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { createModelGuide, getModelGuide, getModelGuides } from "../api/client";
import type { ModelGuide, ModelGuideSummary } from "../types";

const POLL_INTERVAL_MS = 4000;
const MAX_POLL_TRIES = 30;

interface ModelGuidesProps {
  initialMake?: string;
  initialModel?: string;
  initialGuide?: { make?: string; model?: string };
}

interface PendingGuide {
  make: string;
  model: string;
}

function matchesGuide(g: ModelGuideSummary, make: string, model: string): boolean {
  const sameModel = (g.model ?? "").toLowerCase() === model.toLowerCase();
  if (!make) return sameModel;
  return sameModel && (g.make ?? "").toLowerCase() === make.toLowerCase();
}

export function ModelGuides({ initialMake, initialModel, initialGuide }: ModelGuidesProps) {
  const [guides, setGuides] = useState<ModelGuideSummary[]>([]);
  const [selected, setSelected] = useState<ModelGuideSummary | null>(null);
  const [guide, setGuide] = useState<ModelGuide | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  // Create form state.
  const [make, setMake] = useState(initialMake ?? "");
  const [model, setModel] = useState(initialModel ?? "");
  const [pending, setPending] = useState<PendingGuide | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const triesRef = useRef(0);
  const didAutoSelect = useRef(false);

  const refreshGuides = useCallback(async (): Promise<ModelGuideSummary[]> => {
    const g = await getModelGuides();
    setGuides(g);
    return g;
  }, []);

  useEffect(() => {
    refreshGuides()
      .then((g) => {
        if (didAutoSelect.current) return;
        if (initialGuide?.model) {
          const target = g.find(
            (x) =>
              x.status !== "generating" &&
              x.status !== "failed" &&
              matchesGuide(x, initialGuide.make ?? "", initialGuide.model ?? ""),
          );
          if (target) {
            didAutoSelect.current = true;
            setSelected(target);
            return;
          }
        }
        const firstReady = g.find((x) => x.status !== "generating" && x.status !== "failed");
        if (firstReady) setSelected(firstReady);
      })
      .catch(() => setError("Could not load model guides."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadGuide = useCallback(async (summary: ModelGuideSummary) => {
    setSelected(summary);
    setGuide(null);
    setError(null);
    if (!summary.make || !summary.model) return;
    try {
      setGuide(await getModelGuide(summary.make, summary.model));
    } catch {
      setError("Could not load this guide.");
    }
  }, []);

  useEffect(() => {
    if (selected) loadGuide(selected);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.make, selected?.model]);

  const clearPoll = useCallback(() => {
    if (pollTimer.current) {
      clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  useEffect(() => clearPoll, [clearPoll]);

  const poll = useCallback(
    (target: PendingGuide) => {
      triesRef.current += 1;
      getModelGuides()
        .then((g) => {
          setGuides(g);
          const found = g.find((x) => matchesGuide(x, target.make, target.model));
          if (found && found.status === "ready") {
            setPending(null);
            clearPoll();
            setSelected(found);
            return;
          }
          if (found && found.status === "failed") {
            setPending(null);
            clearPoll();
            setCreateError(`Generation failed for ${target.make} ${target.model}.`);
            return;
          }
          if (triesRef.current >= MAX_POLL_TRIES) {
            setPending(null);
            clearPoll();
            setCreateError("Generation timed out. Please try again.");
            return;
          }
          pollTimer.current = setTimeout(() => poll(target), POLL_INTERVAL_MS);
        })
        .catch(() => {
          if (triesRef.current >= MAX_POLL_TRIES) {
            setPending(null);
            clearPoll();
            setCreateError("Generation timed out. Please try again.");
            return;
          }
          pollTimer.current = setTimeout(() => poll(target), POLL_INTERVAL_MS);
        });
    },
    [clearPoll],
  );

  const submitCreate = useCallback(
    async (rawMake: string, rawModel: string) => {
      const m = rawMake.trim();
      const mdl = rawModel.trim();
      if (!mdl) return;
      setCreateError(null);
      clearPoll();
      triesRef.current = 0;
      const target = { make: m, model: mdl };
      setPending(target);
      try {
        await createModelGuide(m, mdl);
        pollTimer.current = setTimeout(() => poll(target), POLL_INTERVAL_MS);
      } catch (e) {
        setPending(null);
        clearPoll();
        setCreateError(e instanceof Error ? e.message : "Could not start generation.");
      }
    },
    [clearPoll, poll],
  );

  const onSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      submitCreate(make, model);
    },
    [make, model, submitCreate],
  );

  const q = filter.trim().toLowerCase();
  const visibleGuides = q
    ? guides.filter((g) =>
        [g.make, g.model, g.title]
          .filter(Boolean)
          .some((s) => s!.toLowerCase().includes(q)),
      )
    : guides;

  const pendingShown =
    pending && !guides.some((g) => matchesGuide(g, pending.make, pending.model));

  return (
    <div className="flex gap-6">
      <aside className="w-64 shrink-0">
        <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
          Model guides
        </h2>

        <form onSubmit={onSubmit} className="mb-3 space-y-2 rounded-md border border-slate-200 bg-white p-2">
          <div className="flex gap-2">
            <input
              value={make}
              onChange={(e) => setMake(e.target.value)}
              placeholder="Make"
              aria-label="Make"
              className="w-1/2 rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-700"
            />
            <input
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="Model"
              aria-label="Model"
              className="w-1/2 rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-700"
            />
          </div>
          <button
            type="submit"
            disabled={pending !== null || model.trim() === ""}
            className="w-full rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-700 disabled:bg-slate-300"
          >
            + Create guide
          </button>
        </form>

        {createError && (
          <div className="mb-2 rounded-md border border-rose-200 bg-rose-50 p-2 text-xs text-rose-700">
            {createError}
            <button
              type="button"
              onClick={() => submitCreate(make, model)}
              className="ml-2 font-medium underline hover:text-rose-900"
            >
              Retry
            </button>
          </div>
        )}

        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter guides…"
          aria-label="Filter guides"
          className="mb-2 w-full rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-700"
        />

        <ul className="space-y-1">
          {pendingShown && (
            <li className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-slate-500">
              <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-slate-300 border-t-sky-600" />
              Generating {pending!.make} {pending!.model} … (up to ~2 min)
            </li>
          )}
          {visibleGuides.map((g) => {
            const key = `${g.make}/${g.model}`;
            const active = selected?.make === g.make && selected?.model === g.model;
            const isGenerating = g.status === "generating";
            const isFailed = g.status === "failed";
            const disabled = isGenerating || isFailed;
            return (
              <li key={key}>
                <button
                  onClick={() => !disabled && setSelected(g)}
                  disabled={disabled}
                  className={`flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm ${
                    active
                      ? "bg-slate-100 font-medium text-slate-900"
                      : disabled
                        ? "cursor-not-allowed text-slate-400"
                        : "text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  <span className="min-w-0">
                    <span className="block truncate">{g.title}</span>
                    {g.updated && !disabled && (
                      <span className="block text-[10px] text-slate-400">
                        updated {g.updated}
                      </span>
                    )}
                  </span>
                  {isGenerating && (
                    <span className="inline-block h-3 w-3 shrink-0 animate-spin rounded-full border-2 border-slate-300 border-t-sky-600" />
                  )}
                  {isFailed && (
                    <span className="shrink-0 rounded-full bg-rose-100 px-1.5 py-0.5 text-[10px] font-medium text-rose-700">
                      failed
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </aside>

      <article className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white p-6">
        {guides.length === 0 && !pending && (
          <div className="text-slate-500">{error ?? "No model guides yet."}</div>
        )}
        {error && guides.length > 0 && <div className="text-sm text-rose-600">{error}</div>}
        {guides.length > 0 && !error && !guide && selected && (
          <div className="text-slate-400">Loading…</div>
        )}
        {guide && (
          <div className="prose prose-slate prose-sm max-w-none prose-headings:font-semibold prose-a:text-sky-600">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{guide.markdown}</ReactMarkdown>
          </div>
        )}
      </article>
    </div>
  );
}
