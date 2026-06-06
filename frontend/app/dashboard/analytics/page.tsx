"use client";

import { format, parseISO } from "date-fns";
import { useCallback, useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ApiError, getCallAnalytics, type CallAnalyticsResponse } from "@/lib/api";
import { getDashboardOrgId } from "@/lib/config";

const DAY_OPTIONS = [
  { label: "Last 7 days", value: 7 },
  { label: "Last 30 days", value: 30 },
  { label: "Last 90 days", value: 90 },
] as const;

function formatDuration(seconds: number): string {
  if (seconds <= 0) {
    return "0m";
  }
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  if (minutes === 0) {
    return `${remainder}s`;
  }
  return remainder > 0 ? `${minutes}m ${remainder}s` : `${minutes}m`;
}

function formatIssueType(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function StatCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
      <p className="text-sm font-medium text-gray-500 dark:text-slate-400">{label}</p>
      <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-slate-100">{value}</p>
      {hint ? (
        <p className="mt-1 text-xs text-gray-400 dark:text-slate-500">{hint}</p>
      ) : null}
    </div>
  );
}

export default function AnalyticsPage() {
  const orgId = getDashboardOrgId();
  const [days, setDays] = useState<number>(30);
  const [data, setData] = useState<CallAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await getCallAnalytics(orgId, days);
      setData(response);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Failed to load call analytics";
      setError(message);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [days, orgId]);

  useEffect(() => {
    void load();
  }, [load]);

  const hourChartData =
    data?.calls_by_hour.map((item) => ({
      ...item,
      label: `${item.hour}:00`,
    })) ?? [];

  const issueChartData =
    data?.top_issue_types.map((item) => ({
      ...item,
      label: formatIssueType(item.issue_type),
    })) ?? [];

  const sentimentItems = data
    ? [
        { name: "Positive", value: data.sentiment_breakdown.positive, color: "#16a34a" },
        { name: "Neutral", value: data.sentiment_breakdown.neutral, color: "#64748b" },
        { name: "Negative", value: data.sentiment_breakdown.negative, color: "#dc2626" },
      ]
    : [];

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-slate-100">
            Call Analytics
          </h1>
          <p className="text-sm text-gray-500 dark:text-slate-400">
            What your AI receptionist handled — calls, bookings, peak hours, and issue trends.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {DAY_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setDays(option.value)}
              className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                days === option.value
                  ? "bg-blue-600 text-white"
                  : "border border-gray-200 bg-white text-gray-700 hover:bg-gray-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </header>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <div
                key={index}
                className="h-28 animate-pulse rounded-xl bg-gray-100 dark:bg-slate-800"
              />
            ))}
          </div>
          <div className="h-80 animate-pulse rounded-xl bg-gray-100 dark:bg-slate-800" />
        </div>
      ) : data ? (
        <>
          <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Total Calls" value={String(data.summary.total_calls)} />
            <StatCard label="Bookings Made" value={String(data.summary.calls_booked)} />
            <StatCard
              label="Booking Rate"
              value={`${data.summary.booking_rate.toFixed(1)}%`}
            />
            <StatCard
              label="Avg Duration"
              value={formatDuration(data.summary.avg_duration_seconds)}
              hint={`$${data.summary.total_cost_usd.toFixed(2)} total call cost`}
            />
          </section>

          <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
            <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-slate-100">
              Calls Per Day
            </h2>
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={data.calls_by_day}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis
                  dataKey="date"
                  tickFormatter={(value) => format(parseISO(value), "MMM d")}
                  tick={{ fontSize: 11 }}
                />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                <Tooltip
                  labelFormatter={(value) => format(parseISO(String(value)), "MMM d, yyyy")}
                />
                <Line
                  type="monotone"
                  dataKey="count"
                  stroke="#2563eb"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  name="Calls"
                />
              </LineChart>
            </ResponsiveContainer>
          </section>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
              <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-slate-100">
                Calls By Hour
              </h2>
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={hourChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis
                    dataKey="hour"
                    tick={{ fontSize: 10 }}
                    tickFormatter={(hour) => {
                      const value = Number(hour);
                      if (value % 3 !== 0) {
                        return "";
                      }
                      if (value === 0) {
                        return "12am";
                      }
                      if (value === 12) {
                        return "12pm";
                      }
                      if (value < 12) {
                        return `${value}am`;
                      }
                      return `${value - 12}pm`;
                    }}
                  />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#2563eb" radius={[4, 4, 0, 0]} name="Calls" />
                </BarChart>
              </ResponsiveContainer>
            </section>

            <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
              <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-slate-100">
                Top Issue Types
              </h2>
              {issueChartData.length === 0 ? (
                <p className="py-16 text-center text-sm text-gray-500 dark:text-slate-400">
                  No dispatch jobs recorded in this period.
                </p>
              ) : (
                <ResponsiveContainer width="100%" height={320}>
                  <BarChart data={issueChartData} layout="vertical" margin={{ left: 24 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
                    <YAxis
                      type="category"
                      dataKey="label"
                      width={120}
                      tick={{ fontSize: 11 }}
                    />
                    <Tooltip />
                    <Bar dataKey="count" fill="#0ea5e9" radius={[0, 4, 4, 0]} name="Jobs" />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </section>
          </div>

          <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
            <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-slate-100">
              Sentiment Breakdown
            </h2>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              {sentimentItems.map((item) => (
                <div
                  key={item.name}
                  className="rounded-lg border border-gray-100 p-4 dark:border-slate-800"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="inline-block h-3 w-3 rounded-full"
                      style={{ backgroundColor: item.color }}
                    />
                    <p className="text-sm font-medium text-gray-600 dark:text-slate-300">
                      {item.name}
                    </p>
                  </div>
                  <p className="mt-2 text-2xl font-bold text-gray-900 dark:text-slate-100">
                    {item.value}
                  </p>
                </div>
              ))}
            </div>
            <div className="mt-6 h-4 overflow-hidden rounded-full bg-gray-100 dark:bg-slate-800">
              <div className="flex h-full w-full">
                {sentimentItems.map((item) => {
                  const total =
                    data.sentiment_breakdown.positive +
                    data.sentiment_breakdown.neutral +
                    data.sentiment_breakdown.negative;
                  const width = total > 0 ? (item.value / total) * 100 : 0;
                  return width > 0 ? (
                    <div
                      key={item.name}
                      style={{ width: `${width}%`, backgroundColor: item.color }}
                    />
                  ) : null;
                })}
              </div>
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}
