"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import {
  disconnectGoogleCalendar,
  getGoogleCalendarStatus,
  getGoogleConnectUrl,
  syncGoogleCalendar,
  type GoogleCalendarStatus,
} from "@/lib/api";
import { getDashboardOrgId } from "@/lib/config";

function formatDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export default function IntegrationsPage() {
  const orgId = getDashboardOrgId();
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<GoogleCalendarStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<{ type: "success" | "error"; message: string } | null>(
    null,
  );
  const [syncing, setSyncing] = useState(false);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getGoogleCalendarStatus(orgId);
      setStatus(data);
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
    if (connected !== "google" || !oauthStatus) return;
    if (oauthStatus === "success") {
      setBanner({ type: "success", message: "Google Calendar connected successfully." });
      void loadStatus();
    } else {
      const reason = searchParams.get("reason") ?? "unknown";
      setBanner({
        type: "error",
        message: `Google Calendar connection failed: ${reason}`,
      });
    }
  }, [searchParams, loadStatus]);

  const handleConnect = async () => {
    try {
      const { authorization_url } = await getGoogleConnectUrl(orgId);
      window.location.href = authorization_url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start OAuth");
    }
  };

  const handleSync = async () => {
    const techId = status?.calendars[0]?.technician_id;
    if (!techId) {
      setError("No technician-linked calendar to sync");
      return;
    }
    setSyncing(true);
    setError(null);
    try {
      const from = new Date();
      const to = new Date();
      to.setDate(to.getDate() + 14);
      const result = await syncGoogleCalendar(
        orgId,
        techId,
        formatDate(from),
        formatDate(to),
      );
      setBanner({
        type: "success",
        message: `Synced ${result.synced} calendar event(s) into availability.`,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  const handleDisconnect = async (email: string) => {
    try {
      await disconnectGoogleCalendar(orgId, email);
      setBanner({ type: "success", message: `Disconnected ${email}.` });
      await loadStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Disconnect failed");
    }
  };

  const connected = status?.connected ?? false;
  const calendars = status?.calendars ?? [];

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
            {connected && (
              <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-900 dark:text-green-200">
                Connected
              </span>
            )}
          </div>
          <p className="mb-4 text-sm text-gray-600 dark:text-slate-400">
            Sync technician schedules with Google Calendar. Bookings appear
            automatically and external events block availability.
          </p>

          {loading ? (
            <p className="text-sm text-gray-500">Loading…</p>
          ) : connected ? (
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
                  onClick={() => void handleSync()}
                  disabled={syncing}
                  className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {syncing ? "Syncing…" : "Sync Now"}
                </button>
                {calendars[0]?.email && (
                  <button
                    type="button"
                    onClick={() => void handleDisconnect(calendars[0].email)}
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
              onClick={() => void handleConnect()}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
            >
              Connect Google Calendar
            </button>
          )}
        </div>

        <div className="rounded-xl border border-gray-200 bg-gray-50 p-6 opacity-75 dark:border-slate-700 dark:bg-slate-800/50">
          <div className="mb-4 flex items-start justify-between">
            <h2 className="text-lg font-semibold text-gray-500 dark:text-slate-400">Jobber</h2>
            <span className="rounded-full bg-gray-200 px-2 py-0.5 text-xs font-medium text-gray-600 dark:bg-slate-700 dark:text-slate-400">
              Coming Soon
            </span>
          </div>
          <p className="text-sm text-gray-500 dark:text-slate-500">
            Import customers, jobs, and technician schedules from Jobber. Coming
            soon.
          </p>
        </div>
      </div>
    </div>
  );
}
