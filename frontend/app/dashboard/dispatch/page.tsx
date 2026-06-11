"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { DispatchBoard } from "@/components/DispatchBoard";
import { getScheduledJobs, type ScheduledJob } from "@/lib/api";
import { formatInOrgTimezone, orgLocalDateKey, orgLocalTimeParts } from "@/lib/datetime";

type ViewMode = "list" | "calendar";

const CALENDAR_START_HOUR = 7;
const CALENDAR_END_HOUR = 19;
const HOUR_ROW_PX = 48;
const CALENDAR_HOURS = CALENDAR_END_HOUR - CALENDAR_START_HOUR;

function isoDate(d: Date): string {
  return orgLocalDateKey(d);
}

function startOfWeekMonday(d: Date): Date {
  const date = new Date(d);
  const day = date.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  date.setDate(date.getDate() + diff);
  date.setHours(0, 0, 0, 0);
  return date;
}

function addDays(d: Date, days: number): Date {
  const next = new Date(d);
  next.setDate(next.getDate() + days);
  return next;
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function formatWeekRange(weekStart: Date): string {
  const weekEnd = addDays(weekStart, 6);
  const opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  const startStr = formatInOrgTimezone(weekStart, opts);
  const endStr = formatInOrgTimezone(weekEnd, { ...opts, year: "numeric" });
  return `${startStr} – ${endStr}`;
}

function formatHourLabel(hour: number): string {
  const h = hour % 12 || 12;
  const suffix = hour < 12 ? "AM" : "PM";
  return `${h} ${suffix}`;
}

function friendlyIssueType(issue: string): string {
  return issue
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1)}…`;
}

function technicianColors(name?: string): string {
  const key = (name ?? "").toLowerCase();
  if (key.includes("elena")) {
    return "bg-indigo-100 text-indigo-900 border-indigo-200 dark:bg-indigo-950 dark:text-indigo-200 dark:border-indigo-800";
  }
  if (key.includes("marcus")) {
    return "bg-orange-100 text-orange-900 border-orange-200 dark:bg-orange-950 dark:text-orange-200 dark:border-orange-800";
  }
  return "bg-teal-100 text-teal-900 border-teal-200 dark:bg-teal-950 dark:text-teal-200 dark:border-teal-800";
}

function jobBlockPosition(job: ScheduledJob): { top: number; height: number } | null {
  if (!job.scheduled_window_start) return null;
  const startParts = orgLocalTimeParts(job.scheduled_window_start);
  const endParts = job.scheduled_window_end
    ? orgLocalTimeParts(job.scheduled_window_end)
    : { hours: startParts.hours + 1, minutes: startParts.minutes };

  const startMinutes = startParts.hours * 60 + startParts.minutes;
  const endMinutes = endParts.hours * 60 + endParts.minutes;
  const rangeStart = CALENDAR_START_HOUR * 60;
  const rangeEnd = CALENDAR_END_HOUR * 60;
  const totalMinutes = rangeEnd - rangeStart;

  const clampedStart = Math.max(startMinutes, rangeStart);
  const clampedEnd = Math.min(endMinutes, rangeEnd);
  if (clampedEnd <= clampedStart) return null;

  const top = ((clampedStart - rangeStart) / totalMinutes) * 100;
  const height = ((clampedEnd - clampedStart) / totalMinutes) * 100;
  return { top, height: Math.max(height, 4) };
}

function DispatchWeekCalendar({
  jobs,
  weekStart,
  loading,
  onPrevWeek,
  onNextWeek,
  onRefresh,
  refreshing,
}: {
  jobs: ScheduledJob[];
  weekStart: Date;
  loading: boolean;
  onPrevWeek: () => void;
  onNextWeek: () => void;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  const today = useMemo(() => new Date(), []);
  const weekDays = useMemo(
    () => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)),
    [weekStart],
  );
  const hourLabels = useMemo(
    () => Array.from({ length: CALENDAR_HOURS }, (_, i) => CALENDAR_START_HOUR + i),
    [],
  );
  const calendarHeight = CALENDAR_HOURS * HOUR_ROW_PX;

  const jobsByDay = useMemo(() => {
    const map = new Map<string, ScheduledJob[]>();
    for (const day of weekDays) {
      map.set(isoDate(day), []);
    }
    for (const job of jobs) {
      if (!job.scheduled_window_start) continue;
      const key = isoDate(new Date(job.scheduled_window_start));
      if (map.has(key)) {
        map.get(key)!.push(job);
      }
    }
    return map;
  }, [jobs, weekDays]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onPrevWeek}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50 dark:border-slate-700 dark:hover:bg-slate-800"
            aria-label="Previous week"
          >
            ←
          </button>
          <h2 className="text-base font-semibold text-gray-900 dark:text-slate-100">
            {formatWeekRange(weekStart)}
          </h2>
          <button
            type="button"
            onClick={onNextWeek}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50 dark:border-slate-700 dark:hover:bg-slate-800"
            aria-label="Next week"
          >
            →
          </button>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
          className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
        >
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {loading ? (
        <div
          className="animate-pulse rounded-xl bg-gray-100 dark:bg-slate-800"
          style={{ height: calendarHeight + 48 }}
        />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="min-w-[56rem]">
            <div className="grid grid-cols-[3.5rem_repeat(7,minmax(7rem,1fr))] border-b border-gray-200 dark:border-slate-800">
              <div className="border-r border-gray-200 dark:border-slate-800" />
              {weekDays.map((day) => {
                const isToday = isSameDay(day, today);
                return (
                  <div
                    key={isoDate(day)}
                    className={`border-r border-gray-200 px-2 py-3 text-center last:border-r-0 dark:border-slate-800 ${
                      isToday
                        ? "bg-blue-50 dark:bg-blue-950/40"
                        : "bg-gray-50 dark:bg-slate-800/50"
                    }`}
                  >
                    <p
                      className={`text-xs font-medium uppercase tracking-wide ${
                        isToday
                          ? "text-blue-700 dark:text-blue-300"
                          : "text-gray-500 dark:text-slate-400"
                      }`}
                    >
                      {day.toLocaleDateString(undefined, { weekday: "short" })}
                    </p>
                    <p
                      className={`text-sm font-semibold ${
                        isToday
                          ? "text-blue-900 dark:text-blue-100"
                          : "text-gray-900 dark:text-slate-100"
                      }`}
                    >
                      {day.toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                    </p>
                  </div>
                );
              })}
            </div>

            <div className="grid grid-cols-[3.5rem_repeat(7,minmax(7rem,1fr))]">
              <div className="relative border-r border-gray-200 dark:border-slate-800">
                {hourLabels.map((hour) => (
                  <div
                    key={hour}
                    className="flex items-start justify-end border-b border-gray-100 pr-2 pt-1 text-xs text-gray-400 dark:border-slate-800 dark:text-slate-500"
                    style={{ height: HOUR_ROW_PX }}
                  >
                    {formatHourLabel(hour)}
                  </div>
                ))}
              </div>

              {weekDays.map((day) => {
                const dayKey = isoDate(day);
                const dayJobs = jobsByDay.get(dayKey) ?? [];
                const isToday = isSameDay(day, today);

                return (
                  <div
                    key={dayKey}
                    className={`relative border-r border-gray-200 last:border-r-0 dark:border-slate-800 ${
                      isToday ? "bg-blue-50/30 dark:bg-blue-950/10" : ""
                    }`}
                    style={{ height: calendarHeight }}
                  >
                    {hourLabels.map((hour, index) => (
                      <div
                        key={hour}
                        className="absolute left-0 right-0 border-b border-gray-100 dark:border-slate-800"
                        style={{ top: index * HOUR_ROW_PX, height: HOUR_ROW_PX }}
                      />
                    ))}

                    {dayJobs.map((job) => {
                      const pos = jobBlockPosition(job);
                      if (!pos) return null;
                      return (
                        <div
                          key={job.job_id}
                          className={`absolute left-1 right-1 overflow-hidden rounded-md border px-1.5 py-1 text-xs shadow-sm ${technicianColors(
                            job.technician_name,
                          )}`}
                          style={{
                            top: `${pos.top}%`,
                            height: `${pos.height}%`,
                            minHeight: "2.5rem",
                          }}
                          title={`${job.customer_name} — ${job.job_number}`}
                        >
                          <p className="truncate font-semibold leading-tight">
                            {truncate(job.customer_name, 18)}
                          </p>
                          <p className="truncate leading-tight opacity-90">
                            {friendlyIssueType(job.issue_type)}
                          </p>
                          <p className="truncate leading-tight opacity-80">
                            {job.technician_name ?? "Unassigned"}
                          </p>
                          <p className="truncate font-mono text-[10px] leading-tight opacity-70">
                            {job.job_number}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function DispatchPage() {
  const [view, setView] = useState<ViewMode>("list");
  const [todayJobs, setTodayJobs] = useState<ScheduledJob[]>([]);
  const [upcomingJobs, setUpcomingJobs] = useState<ScheduledJob[]>([]);
  const [weekJobs, setWeekJobs] = useState<ScheduledJob[]>([]);
  const [weekAnchor, setWeekAnchor] = useState(() => new Date());
  const [loading, setLoading] = useState(true);
  const [weekLoading, setWeekLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const weekStart = useMemo(() => startOfWeekMonday(weekAnchor), [weekAnchor]);
  const weekEnd = useMemo(() => addDays(weekStart, 6), [weekStart]);

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const today = new Date();
      const weekEndDate = new Date();
      weekEndDate.setDate(weekEndDate.getDate() + 7);
      const [todayResp, upcomingResp] = await Promise.all([
        getScheduledJobs(isoDate(today), isoDate(today)),
        getScheduledJobs(isoDate(today), isoDate(weekEndDate)),
      ]);
      setTodayJobs(todayResp.items);
      setUpcomingJobs(upcomingResp.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dispatch jobs");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadWeek = useCallback(async () => {
    setWeekJobs([]);
    setWeekLoading(true);
    setError(null);
    try {
      const resp = await getScheduledJobs(isoDate(weekStart), isoDate(weekEnd));
      setWeekJobs(resp.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load calendar jobs");
    } finally {
      setWeekLoading(false);
    }
  }, [weekStart, weekEnd]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    if (view === "calendar") {
      void loadWeek();
    }
  }, [view, loadWeek]);

  const handleRefresh = useCallback(() => {
    if (view === "list") {
      void loadList();
    } else {
      void loadWeek();
    }
  }, [view, loadList, loadWeek]);

  const refreshing = view === "list" ? loading : weekLoading;

  return (
    <div className="space-y-8">
      <header className="space-y-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-slate-100">Dispatch</h1>
          <p className="text-sm text-gray-500 dark:text-slate-400">
            Today&apos;s schedule and upcoming jobs for the next 7 days.
          </p>
        </div>

        <div className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-1 dark:border-slate-700 dark:bg-slate-800">
          <button
            type="button"
            onClick={() => setView("list")}
            className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              view === "list"
                ? "bg-white text-gray-900 shadow-sm dark:bg-slate-900 dark:text-slate-100"
                : "text-gray-600 hover:text-gray-900 dark:text-slate-400 dark:hover:text-slate-100"
            }`}
          >
            List view
          </button>
          <button
            type="button"
            onClick={() => setView("calendar")}
            className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              view === "calendar"
                ? "bg-white text-gray-900 shadow-sm dark:bg-slate-900 dark:text-slate-100"
                : "text-gray-600 hover:text-gray-900 dark:text-slate-400 dark:hover:text-slate-100"
            }`}
          >
            Calendar view
          </button>
        </div>
      </header>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {error}
        </div>
      )}

      {view === "list" ? (
        <>
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
              <DispatchBoard jobs={todayJobs} onRefresh={handleRefresh} refreshing={refreshing} />
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
                onRefresh={handleRefresh}
                refreshing={refreshing}
              />
            )}
          </section>
        </>
      ) : (
        <DispatchWeekCalendar
          jobs={weekJobs}
          weekStart={weekStart}
          loading={weekLoading}
          onPrevWeek={() => setWeekAnchor((d) => addDays(d, -7))}
          onNextWeek={() => setWeekAnchor((d) => addDays(d, 7))}
          onRefresh={handleRefresh}
          refreshing={refreshing}
        />
      )}
    </div>
  );
}
