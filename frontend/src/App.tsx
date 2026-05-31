import { useEffect, useState } from "react";
import { getHealth } from "./api/client";
import { Dashboard } from "./pages/Dashboard";

type HealthState = "checking" | "ok" | "down";

export default function App() {
  const [health, setHealth] = useState<HealthState>("checking");

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
          <h1 className="text-xl font-semibold tracking-tight">
            🚗 CarCatcher
          </h1>
          <HealthPill state={health} />
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Dashboard />
      </main>
    </div>
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
