"use client";

import { useCallback, useEffect, useState } from "react";

import { getSystemHealth, type SystemHealthResponse } from "@/lib/api";

function statusColor(status: string): string {
  if (status === "ok" || status === "healthy") {
    return "text-green-700 bg-green-100 dark:bg-green-950 dark:text-green-200";
  }
  if (status === "degraded") {
    return "text-amber-800 bg-amber-100 dark:bg-amber-950 dark:text-amber-200";
  }
  return "text-red-800 bg-red-100 dark:bg-red-950 dark:text-red-200";
}

export default function HealthPage() {
  const [health, setHealth] = useState<SystemHealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setHealth(await getSystemHealth());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Health check failed");
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 30_000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div className="p-8">
      <h1 className="mb-2 text-2xl font-bold text-gray-900 dark:text-slate-100">
        System Health
      </h1>
      <p className="mb-6 text-sm text-gray-600 dark:text-slate-400">
        Auto-refreshes every 30 seconds.
        {health?.timestamp && (
          <span className="ml-2">
            Last checked: {new Date(health.timestamp).toLocaleString()}
          </span>
        )}
      </p>

      {error && (
        <p className="mb-4 text-sm text-red-700 dark:text-red-300">{error}</p>
      )}

      {health && (
        <>
          <span
            className={`mb-6 inline-block rounded-full px-4 py-1 text-sm font-medium ${statusColor(health.status)}`}
          >
            Overall: {health.status}
          </span>

          <div className="mb-8 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {Object.entries(health.components).map(([name, comp]) => (
              <div
                key={name}
                className="rounded-xl border border-gray-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
              >
                <p className="text-xs uppercase text-gray-500">{name}</p>
                <p
                  className={`mt-2 inline-block rounded px-2 py-0.5 text-sm ${statusColor(comp.status)}`}
                >
                  {comp.status}
                </p>
                {comp.latency_ms != null && (
                  <p className="mt-2 text-sm text-gray-600 dark:text-slate-400">
                    {comp.latency_ms} ms
                  </p>
                )}
                {comp.vector_count != null && (
                  <p className="mt-1 text-sm">Vectors: {comp.vector_count}</p>
                )}
                {comp.last_call_at && (
                  <p className="mt-1 text-xs text-gray-500">
                    Last call: {new Date(comp.last_call_at).toLocaleString()}
                  </p>
                )}
              </div>
            ))}
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              label="Organizations"
              value={health.metrics.total_organizations}
            />
            <MetricCard label="Customers" value={health.metrics.total_customers} />
            <MetricCard
              label="Calls today"
              value={health.metrics.total_calls_today}
            />
            <MetricCard
              label="Open dispatch jobs"
              value={health.metrics.total_dispatch_jobs_open}
            />
          </div>
        </>
      )}
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-gray-900 dark:text-slate-100">
        {value}
      </p>
    </div>
  );
}
