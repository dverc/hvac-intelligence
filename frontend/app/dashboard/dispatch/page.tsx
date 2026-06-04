"use client";

import { useCallback, useEffect, useState } from "react";

import { DispatchBoard } from "@/components/DispatchBoard";
import { getScheduledJobs, type ScheduledJob } from "@/lib/api";

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export default function DispatchPage() {
  const [todayJobs, setTodayJobs] = useState<ScheduledJob[]>([]);
  const [upcomingJobs, setUpcomingJobs] = useState<ScheduledJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const today = new Date();
      const weekEnd = new Date();
      weekEnd.setDate(weekEnd.getDate() + 7);
      const [todayResp, upcomingResp] = await Promise.all([
        getScheduledJobs(isoDate(today), isoDate(today)),
        getScheduledJobs(isoDate(today), isoDate(weekEnd)),
      ]);
      setTodayJobs(todayResp.items);
      setUpcomingJobs(upcomingResp.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dispatch jobs");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-slate-100">Dispatch</h1>
        <p className="text-sm text-gray-500 dark:text-slate-400">
          Today&apos;s schedule and upcoming jobs for the next 7 days.
        </p>
      </header>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {error}
        </div>
      )}

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100">
          Today&apos;s Jobs
        </h2>
        {loading ? (
          <div className="h-32 animate-pulse rounded bg-gray-100 dark:bg-slate-800" />
        ) : todayJobs.length === 0 ? (
          <p className="rounded-xl border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500 dark:border-slate-700 dark:text-slate-400">
            No jobs scheduled for today.
          </p>
        ) : (
          <DispatchBoard jobs={todayJobs} onRefresh={load} refreshing={loading} />
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100">
          Upcoming (7 days)
        </h2>
        {loading ? (
          <div className="h-32 animate-pulse rounded bg-gray-100 dark:bg-slate-800" />
        ) : (
          <DispatchBoard
            jobs={upcomingJobs}
            groupByDate
            onRefresh={load}
            refreshing={loading}
          />
        )}
      </section>
    </div>
  );
}
