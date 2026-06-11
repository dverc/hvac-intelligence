"use client";

import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  buildDisclosureText,
  createOutboundCampaign,
  executeOutboundCampaign,
  listBlockedAttempts,
  listOutboundCampaigns,
  previewEligibleCustomers,
  updateOutboundCampaignStatus,
  type BlockedAttempt,
  type OutboundCampaign,
} from "@/lib/api";
import { getOrgName } from "@/lib/config";

function resolveOrgDisplayName(): string {
  const name = getOrgName();
  if (name && name !== "HVAC Intelligence") {
    return name;
  }
  return "Your HVAC Company";
}

const CAMPAIGN_TYPES = [
  { value: "REACTIVATION", label: "Reactivation" },
  { value: "RETENTION", label: "Retention" },
  { value: "REMINDER", label: "Reminder" },
] as const;

const HOUR_OPTIONS = Array.from({ length: 14 }, (_, i) => i + 8);

function statusBadgeClass(status: string): string {
  switch (status) {
    case "ACTIVE":
      return "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300";
    case "PAUSED":
      return "bg-yellow-100 text-yellow-800 dark:bg-yellow-950 dark:text-yellow-300";
    case "COMPLETED":
      return "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300";
    default:
      return "bg-gray-100 text-gray-700 dark:bg-slate-800 dark:text-slate-300";
  }
}

export default function OutboundPage() {
  const [campaigns, setCampaigns] = useState<OutboundCampaign[]>([]);
  const [blocked, setBlocked] = useState<BlockedAttempt[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [previewCount, setPreviewCount] = useState<number | null>(null);
  const [disclosurePreview, setDisclosurePreview] = useState("");

  const [form, setForm] = useState({
    campaign_name: "",
    campaign_type: "REACTIVATION",
    churn_score_threshold: 0.75,
    max_attempts: 2,
    calling_hours_start: 9,
    calling_hours_end: 18,
    disclosure_style: "FRIENDLY",
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [campaignRows, blockedRows] = await Promise.all([
        listOutboundCampaigns(),
        listBlockedAttempts(),
      ]);
      setCampaigns(campaignRows);
      setBlocked(blockedRows);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load outbound data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setDisclosurePreview(
      buildDisclosureText(resolveOrgDisplayName(), form.disclosure_style),
    );
  }, [form.disclosure_style]);

  async function handlePreview() {
    const res = await previewEligibleCustomers(
      form.churn_score_threshold,
      form.max_attempts,
    );
    setPreviewCount(res.eligible_count);
  }

  async function handleCreate() {
    setError(null);
    try {
      await createOutboundCampaign({
        campaign_name: form.campaign_name,
        campaign_type: form.campaign_type,
        churn_score_threshold: form.churn_score_threshold,
        max_attempts: form.max_attempts,
        calling_hours_start: form.calling_hours_start,
        calling_hours_end: form.calling_hours_end,
        disclosure_style: form.disclosure_style,
      });
      setForm((f) => ({ ...f, campaign_name: "" }));
      setPreviewCount(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create campaign");
    }
  }

  async function handleStatusChange(campaignId: string, status: string) {
    await updateOutboundCampaignStatus(campaignId, status);
    await load();
  }

  async function handleExecute(campaignId: string) {
    await executeOutboundCampaign(campaignId);
    await load();
  }

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-slate-100">
          Outbound Campaigns
        </h1>
        <p className="text-sm text-gray-500 dark:text-slate-400">
          AI-powered proactive customer retention — TCPA compliant
        </p>
      </header>

      <section
        role="status"
        className="rounded-xl border border-green-200 bg-green-50 p-4 text-sm text-green-900 dark:border-green-900 dark:bg-green-950/40 dark:text-green-200"
      >
        Compliance Active — AI disclosure, recording consent, DNC checks, and calling
        hours (8AM–9PM local) are enforced on every call.
      </section>

      {error && (
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
      )}

      <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-slate-100">
          Create Campaign
        </h2>
        <div className="grid gap-4 md:grid-cols-2">
          <input
            className="rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
            placeholder="Campaign name"
            value={form.campaign_name}
            onChange={(e) => setForm((f) => ({ ...f, campaign_name: e.target.value }))}
          />
          <select
            className="rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
            value={form.campaign_type}
            onChange={(e) => setForm((f) => ({ ...f, campaign_type: e.target.value }))}
          >
            {CAMPAIGN_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
          <div className="md:col-span-2">
            <label className="text-sm text-gray-600 dark:text-slate-400">
              Churn score threshold: {(form.churn_score_threshold * 100).toFixed(0)}%
            </label>
            <input
              type="range"
              min={0.6}
              max={0.9}
              step={0.01}
              value={form.churn_score_threshold}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  churn_score_threshold: parseFloat(e.target.value),
                }))
              }
              className="w-full"
            />
            <p className="text-xs text-gray-500">
              Target customers above {(form.churn_score_threshold * 100).toFixed(0)}%
              churn risk
            </p>
          </div>
          <select
            className="rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
            value={form.max_attempts}
            onChange={(e) =>
              setForm((f) => ({ ...f, max_attempts: parseInt(e.target.value, 10) }))
            }
          >
            <option value={1}>1 attempt per 30 days</option>
            <option value={2}>2 attempts per 30 days</option>
            <option value={3}>3 attempts per 30 days</option>
          </select>
          <div className="flex gap-2">
            <select
              className="flex-1 rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
              value={form.calling_hours_start}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  calling_hours_start: parseInt(e.target.value, 10),
                }))
              }
            >
              {HOUR_OPTIONS.map((h) => (
                <option key={`start-${h}`} value={h}>
                  Start {h > 12 ? h - 12 : h} {h >= 12 ? "PM" : "AM"}
                </option>
              ))}
            </select>
            <select
              className="flex-1 rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
              value={form.calling_hours_end}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  calling_hours_end: parseInt(e.target.value, 10),
                }))
              }
            >
              {HOUR_OPTIONS.filter((h) => h > form.calling_hours_start).map((h) => (
                <option key={`end-${h}`} value={h}>
                  End {h > 12 ? h - 12 : h} {h >= 12 ? "PM" : "AM"}
                </option>
              ))}
            </select>
          </div>
          <div className="md:col-span-2">
            <p className="mb-2 text-sm font-medium text-gray-700 dark:text-slate-300">
              Disclosure style
            </p>
            <div className="flex gap-4">
              {(["FRIENDLY", "FORMAL"] as const).map((style) => (
                <label key={style} className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="disclosure_style"
                    checked={form.disclosure_style === style}
                    onChange={() => setForm((f) => ({ ...f, disclosure_style: style }))}
                  />
                  {style === "FRIENDLY" ? "Friendly" : "Formal"}
                </label>
              ))}
            </div>
            <p className="mt-3 rounded-lg bg-gray-50 p-3 text-sm italic text-gray-700 dark:bg-slate-800 dark:text-slate-300">
              &ldquo;{disclosurePreview}&rdquo;
            </p>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => void handlePreview()}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium dark:border-slate-600"
          >
            Preview eligible customers
            {previewCount !== null ? ` (${previewCount})` : ""}
          </button>
          <button
            type="button"
            disabled={!form.campaign_name}
            onClick={() => void handleCreate()}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            Create Campaign
          </button>
        </div>
      </section>

      <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-slate-100">
          Active Campaigns
        </h2>
        {loading ? (
          <div className="h-24 animate-pulse rounded-lg bg-gray-100 dark:bg-slate-800" />
        ) : campaigns.length === 0 ? (
          <p className="text-sm text-gray-500">No campaigns yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b text-gray-500 dark:text-slate-400">
                  <th className="py-2 pr-4">Name</th>
                  <th className="py-2 pr-4">Type</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Targeted</th>
                  <th className="py-2 pr-4">Called</th>
                  <th className="py-2 pr-4">Booked</th>
                  <th className="py-2 pr-4">Conversion</th>
                  <th className="py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((c) => (
                  <tr key={c.campaign_id} className="border-b dark:border-slate-800">
                    <td className="py-3 pr-4 font-medium">{c.campaign_name}</td>
                    <td className="py-3 pr-4">{c.campaign_type}</td>
                    <td className="py-3 pr-4">
                      <span
                        className={`rounded-full px-2 py-1 text-xs font-semibold ${statusBadgeClass(c.status)}`}
                      >
                        {c.status}
                      </span>
                    </td>
                    <td className="py-3 pr-4">{c.total_customers_targeted}</td>
                    <td className="py-3 pr-4">{c.total_calls_made}</td>
                    <td className="py-3 pr-4">{c.total_booked}</td>
                    <td className="py-3 pr-4">{c.conversion_rate.toFixed(1)}%</td>
                    <td className="py-3">
                      <div className="flex flex-wrap gap-2">
                        {c.status !== "ACTIVE" && (
                          <button
                            type="button"
                            onClick={() => void handleStatusChange(c.campaign_id, "ACTIVE")}
                            className="text-xs text-green-600 hover:underline"
                          >
                            Activate
                          </button>
                        )}
                        {c.status === "ACTIVE" && (
                          <button
                            type="button"
                            onClick={() => void handleStatusChange(c.campaign_id, "PAUSED")}
                            className="text-xs text-yellow-600 hover:underline"
                          >
                            Pause
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => void handleExecute(c.campaign_id)}
                          className="text-xs text-indigo-600 hover:underline"
                        >
                          Execute
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-slate-100">
          Compliance Log (last 20 blocked attempts)
        </h2>
        {blocked.length === 0 ? (
          <p className="text-sm text-gray-500">No blocked attempts recorded.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b text-gray-500 dark:text-slate-400">
                  <th className="py-2 pr-4">Customer</th>
                  <th className="py-2 pr-4">Block reason</th>
                  <th className="py-2">Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {blocked.map((row) => (
                  <tr key={row.attempt_id} className="border-b dark:border-slate-800">
                    <td className="py-3 pr-4">{row.customer_name}</td>
                    <td className="py-3 pr-4">{row.block_reason}</td>
                    <td className="py-3">{new Date(row.timestamp).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
