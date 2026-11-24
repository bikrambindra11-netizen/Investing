"use client";

import { useEffect, useState } from "react";
import { API_BASE, type Health } from "@/lib/api";

export default function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/health`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setHealth)
      .catch((e) => setError(`Backend not reachable at ${API_BASE} (${e.message})`));
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Setup check</h1>
      <p className="text-slate-600">
        Phase 1 skeleton. The market page arrives in Phase 2.
      </p>

      {error && <div className="rounded border border-red-300 bg-red-50 p-4 text-red-800">{error}</div>}
      {!health && !error && <div className="text-slate-500">Checking backend…</div>}

      {health && (
        <div className="rounded border bg-white p-4">
          <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-2 text-sm">
            <dt className="text-slate-500">Backend</dt>
            <dd className="font-medium text-green-700">{health.status}</dd>
            <dt className="text-slate-500">Database</dt>
            <dd>{health.database}</dd>
            <dt className="text-slate-500">Instruments loaded</dt>
            <dd>{health.instruments}</dd>
            <dt className="text-slate-500">As of</dt>
            <dd>{new Date(health.time).toLocaleString("en-IN")}</dd>
            {Object.entries(health.keys_configured).map(([k, ok]) => (
              <div key={k} className="contents">
                <dt className="text-slate-500">{k}</dt>
                <dd className={ok ? "text-green-700" : "text-amber-700"}>{ok ? "set" : "not set"}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}
