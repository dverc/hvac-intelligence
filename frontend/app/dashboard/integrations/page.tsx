"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import {
  disconnectGoogleCalendar,
  disconnectJobber,
  getGoogleCalendarStatus,
  getGoogleConnectUrl,
  getJobberConnectUrl,
  getJobberStatus,
  syncGoogleCalendar,
  syncJobberData,
  type GoogleCalendarStatus,
  type JobberStatus,
} from "@/lib/api";
import { getDashboardOrgId } from "@/lib/config";

function formatDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export default function IntegrationsPage() {
  const orgId = getDashboardOrgId();
  const searchParams = useSearchParams();
  const [googleStatus, setGoogleStatus] = useState<GoogleCalendarStatus | null>(null);
  const [jobberStatus, setJobberStatus] = useState<JobberStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<{ type: "success" | "error"; message: string } | null>(
    null,
  );
  const [googleSyncing, setGoogleSyncing] = useState(false);
  const [jobberSyncing, setJobberSyncing] = useState(false);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [gcal, jobber] = await Promise.all([
        getGoogleCalendarStatus(orgId),
        getJobberStatus(orgId),
      ]);
      setGoogleStatus(gcal);
      setJobberStatus(jobber);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load integrations");
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  useEffect(() => {
    const connected = searchParams.get("connected");
    const oauthStatus = searchParams.get("status");
    if (!connected || !oauthStatus) return;

    if (oauthStatus === "success") {
      const label = connected === "google" ? "Google Calendar" : "Jobber";
      setBanner({ type: "success", message: `${label} connected successfully.` });
      void loadStatus();
    } else {
      const reason = searchParams.get("reason") ?? "unknown";
      const label = connected === "google" ? "Google Calendar" : "Jobber";
      setBanner({
        type: "error",
        message: `${label} connection failed: ${reason}`,
      });
    }
  }, [searchParams, loadStatus]);

  const handleGoogleConnect = async () => {
    try {
      const { authorization_url } = await getGoogleConnectUrl(orgId);
      window.location.href = authorization_url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start Google OAuth");
    }
  };

  const handleJobberConnect = async () => {
    try {
      const { authorization_url } = await getJobberConnectUrl(orgId);
      window.location.href = authorization_url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start Jobber OAuth");
    }
  };

  const handleGoogleSync = async () => {
    const techId = googleStatus?.calendars[0]?.technician_id;
    if (!techId) {
      setError("No technician-linked calendar to sync");
      return;
    }
    setGoogleSyncing(true);
    setError(null);
    try {
      const from = new Date();
      const to = new Date();
      to.setDate(to.getDate() + 14);
      const result = await syncGoogleCalendar(orgId, techId, formatDate(from), formatDate(to));
      setBanner({
        type: "success",
        message: `Synced ${result.synced} calendar event(s) into availability.`,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Google sync failed");
    } finally {
      setGoogleSyncing(false);
    }
  };

  const handleJobberSync = async () => {
    setJobberSyncing(true);
    setError(null);
    try {
      const result = await syncJobberData(orgId, "all", 7);
      setBanner({
        type: "success",
        message: `Jobber sync complete — clients: ${result.clients_synced}, users: ${result.users_synced}, jobs: ${result.jobs_synced}.`,
      });
      await loadStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Jobber sync failed");
    } finally {
      setJobberSyncing(false);
    }
  };

  const googleConnected = googleStatus?.connected ?? false;
  const calendars = googleStatus?.calendars ?? [];
  const jobberConnected = jobberStatus?.connected ?? false;

  return (
    <div className="p-8">
      <h1 className="mb-2 text-2xl font-bold text-gray-900 dark:text-slate-100">
        Integrations
      </h1>
      <p className="mb-6 text-sm text-gray-600 dark:text-slate-400">
        Connect external tools to sync schedules and customer data.
      </p>

      {banner && (
        <div
          className={`mb-4 rounded-lg px-4 py-3 text-sm ${
            banner.type === "success"
              ? "bg-green-50 text-green-800 dark:bg-green-950 dark:text-green-200"
              : "bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-200"
          }`}
        >
          {banner.message}
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-950 dark:text-red-200">
          {error}
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <div className="mb-4 flex items-start justify-between">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100">
              Google Calendar
            </h2>
            {googleConnected && (
              <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-900 dark:text-green-200">
                Connected
              </span>
            )}
          </div>
          <p className="mb-4 text-sm text-gray-600 dark:text-slate-400">
            Sync technician schedules with Google Calendar. Bookings appear
            automatically and external events block availability.
          </p>
          <p className="mb-4 text-xs text-amber-700 dark:text-amber-300">
            Google Drive sync (Import → Drive tab) uses the same Google account.
            If you connected before Phase 9, disconnect and reconnect once to
            grant Drive read access.
          </p>

          {loading ? (
            <p className="text-sm text-gray-500">Loading…</p>
          ) : googleConnected ? (
            <div className="space-y-3">
              <ul className="text-sm text-gray-700 dark:text-slate-300">
                {calendars.map((cal) => (
                  <li key={cal.token_id ?? cal.email}>
                    {cal.email}
                    {cal.technician_id ? ` (tech ${cal.technician_id.slice(0, 8)}…)` : ""}
                  </li>
                ))}
              </ul>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void handleGoogleSync()}
                  disabled={googleSyncing}
                  className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {googleSyncing ? "Syncing…" : "Sync Now"}
                </button>
                {calendars[0]?.email && (
                  <button
                    type="button"
                    onClick={() =>
                      void disconnectGoogleCalendar(orgId, calendars[0].email).then(() =>
                        loadStatus(),
                      )
                    }
                    className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
                  >
                    Disconnect
                  </button>
                )}
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => void handleGoogleConnect()}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
            >
              Connect Google Calendar
            </button>
          )}
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <div className="mb-4 flex items-start justify-between">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100">Jobber</h2>
            {jobberConnected && (
              <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-900 dark:text-green-200">
                Connected
              </span>
            )}
          </div>
          <p className="mb-4 text-sm text-gray-600 dark:text-slate-400">
            Import customers, jobs, and technician schedules from Jobber. Dispatch
            bookings sync back to Jobber automatically.
          </p>

          {loading ? (
            <p className="text-sm text-gray-500">Loading…</p>
          ) : jobberConnected ? (
            <div className="space-y-3">
              <p className="text-sm text-gray-700 dark:text-slate-300">
                {jobberStatus?.account_name ?? "Connected account"}
                {jobberStatus?.last_sync_at
                  ? ` — last sync ${new Date(jobberStatus.last_sync_at).toLocaleString()}`
                  : ""}
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void handleJobberSync()}
                  disabled={jobberSyncing}
                  className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {jobberSyncing ? "Syncing…" : "Sync Now"}
                </button>
                <button
                  type="button"
                  onClick={() =>
                    void disconnectJobber(orgId).then(() => {
                      setBanner({ type: "success", message: "Jobber disconnected." });
                      void loadStatus();
                    })
                  }
                  className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
                >
                  Disconnect
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => void handleJobberConnect()}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
            >
              Connect Jobber
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
