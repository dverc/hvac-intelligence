"use client";

import type { ScheduledJob } from "@/lib/api";

const STATUS_STYLES: Record<string, string> = {
  SCHEDULED: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
  IN_PROGRESS: "bg-yellow-100 text-yellow-800 dark:bg-yellow-950 dark:text-yellow-300",
  COMPLETED: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300",
  CANCELLED: "bg-gray-100 text-gray-600 dark:bg-slate-800 dark:text-slate-400",
  RESCHEDULED: "bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-300",
};

function formatWindow(job: ScheduledJob): string {
  if (!job.scheduled_window_start) return "—";
  const start = new Date(job.scheduled_window_start);
  const end = job.scheduled_window_end ? new Date(job.scheduled_window_end) : null;
  const timeFmt = start.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  if (end) {
    const endFmt = end.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    return `${timeFmt} – ${endFmt}`;
  }
  return timeFmt;
}

interface Props {
  jobs: ScheduledJob[];
  groupByDate?: boolean;
  onRefresh?: () => void;
  refreshing?: boolean;
}

export function DispatchBoard({
  jobs,
  groupByDate = false,
  onRefresh,
  refreshing = false,
}: Props) {
  const grouped: Record<string, ScheduledJob[]> = {};
  if (groupByDate) {
    for (const job of jobs) {
      const key = job.scheduled_window_start
        ? new Date(job.scheduled_window_start).toLocaleDateString()
        : "Unscheduled";
      grouped[key] = grouped[key] ?? [];
      grouped[key].push(job);
    }
  }

  const renderTable = (rows: ScheduledJob[]) => (
    <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <table className="min-w-full divide-y divide-gray-200 text-sm dark:divide-slate-800">
        <thead className="bg-gray-50 dark:bg-slate-800">
          <tr>
            <th className="px-4 py-3 text-left font-medium">Time Window</th>
            <th className="px-4 py-3 text-left font-medium">Customer</th>
            <th className="px-4 py-3 text-left font-medium">Issue</th>
            <th className="px-4 py-3 text-left font-medium">Technician</th>
            <th className="px-4 py-3 text-left font-medium">Priority</th>
            <th className="px-4 py-3 text-left font-medium">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 dark:divide-slate-800">
          {rows.map((job) => (
            <tr key={job.job_id}>
              <td className="px-4 py-3">{formatWindow(job)}</td>
              <td className="px-4 py-3">{job.customer_name}</td>
              <td className="px-4 py-3">{job.issue_type}</td>
              <td className="px-4 py-3">{job.technician_name ?? "—"}</td>
              <td className="px-4 py-3">{job.priority}</td>
              <td className="px-4 py-3">
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    STATUS_STYLES[job.job_status] ?? STATUS_STYLES.SCHEDULED
                  }`}
                >
                  {job.job_status}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <div className="space-y-4">
      {onRefresh && (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
          >
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      )}

      {jobs.length === 0 ? (
        <p className="rounded-xl border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500 dark:border-slate-700 dark:text-slate-400">
          No jobs scheduled for this period.
        </p>
      ) : groupByDate ? (
        Object.entries(grouped).map(([day, rows]) => (
          <div key={day} className="space-y-2">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-slate-300">{day}</h3>
            {renderTable(rows)}
          </div>
        ))
      ) : (
        renderTable(jobs)
      )}
    </div>
  );
}
