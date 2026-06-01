import { useCallback, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getModelGuide, getModelGuides } from "../api/client";
import type { ModelGuide, ModelGuideSummary } from "../types";

export function ModelGuides() {
  const [guides, setGuides] = useState<ModelGuideSummary[]>([]);
  const [selected, setSelected] = useState<ModelGuideSummary | null>(null);
  const [guide, setGuide] = useState<ModelGuide | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getModelGuides()
      .then((g) => {
        setGuides(g);
        if (g.length > 0) setSelected(g[0]);
      })
      .catch(() => setError("Could not load model guides."));
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

  if (guides.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-slate-300 p-12 text-center text-slate-500">
        {error ?? "No model guides yet."}
      </div>
    );
  }

  return (
    <div className="flex gap-6">
      <aside className="w-56 shrink-0">
        <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
          Model guides
        </h2>
        <ul className="space-y-1">
          {guides.map((g) => {
            const key = `${g.make}/${g.model}`;
            const active = selected?.make === g.make && selected?.model === g.model;
            return (
              <li key={key}>
                <button
                  onClick={() => setSelected(g)}
                  className={`w-full rounded-md px-3 py-2 text-left text-sm ${
                    active
                      ? "bg-slate-100 font-medium text-slate-900"
                      : "text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  {g.title}
                  {g.updated && (
                    <span className="block text-[10px] text-slate-400">
                      updated {g.updated}
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </aside>

      <article className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white p-6">
        {error && <div className="text-sm text-rose-600">{error}</div>}
        {!error && !guide && <div className="text-slate-400">Loading…</div>}
        {guide && (
          <div className="prose prose-slate prose-sm max-w-none prose-headings:font-semibold prose-a:text-sky-600">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{guide.markdown}</ReactMarkdown>
          </div>
        )}
      </article>
    </div>
  );
}
