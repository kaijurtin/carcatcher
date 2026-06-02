import { useEffect, useState } from "react";
import { getHealth } from "./api/client";
import { Dashboard } from "./pages/Dashboard";
import { SavedSearches } from "./pages/SavedSearches";
import { ModelGuides } from "./pages/ModelGuides";

type HealthState = "checking" | "ok" | "down";
type View = "dashboard" | "searches" | "models";

interface GuideTarget {
  make?: string;
  model: string;
}

export default function App() {
  const [health, setHealth] = useState<HealthState>("checking");
  const [view, setView] = useState<View>("dashboard");
  const [modelGuideTarget, setModelGuideTarget] = useState<GuideTarget | null>(null);

  const openGuide = (model: string, make?: string) => {
    setModelGuideTarget({ make, model });
    setView("models");
  };

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((r) => !cancelled && setHealth(r.status === "ok" ? "ok" : "down"))
      .catch(() => !cancelled && setHealth("down"));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-6">
            <h1 className="text-xl font-semibold tracking-tight">🚗 CarCatcher</h1>
            <nav className="flex gap-1">
              <NavTab label="Dashboard" active={view === "dashboard"} onClick={() => setView("dashboard")} />
              <NavTab label="Saved searches" active={view === "searches"} onClick={() => setView("searches")} />
              <NavTab label="Model guides" active={view === "models"} onClick={() => setView("models")} />
            </nav>
          </div>
          <HealthPill state={health} />
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        {view === "dashboard" && <Dashboard onOpenGuide={openGuide} />}
        {view === "searches" && <SavedSearches />}
        {view === "models" && (
          <ModelGuides
            initialGuide={modelGuideTarget ?? undefined}
          />
        )}
      </main>
    </div>
  );
}

function NavTab({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-md px-3 py-1.5 text-sm font-medium ${
        active ? "bg-slate-100 text-slate-900" : "text-slate-500 hover:text-slate-800"
      }`}
    >
      {label}
    </button>
  );
}

function HealthPill({ state }: { state: HealthState }) {
  const styles: Record<HealthState, string> = {
    checking: "bg-slate-100 text-slate-500",
    ok: "bg-emerald-100 text-emerald-700",
    down: "bg-rose-100 text-rose-700",
  };
  const label: Record<HealthState, string> = {
    checking: "checking…",
    ok: "API healthy",
    down: "API down",
  };
  return (
    <span
      className={`rounded-full px-3 py-1 text-xs font-medium ${styles[state]}`}
    >
      {label[state]}
    </span>
  );
}
