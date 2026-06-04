"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  createOrganization,
  getOrganizations,
  updateOrganizationSettings,
  type OrganizationCreatePayload,
  type OrganizationRecord,
} from "@/lib/api";

const INDUSTRIES = [
  "hvac",
  "plumbing",
  "electrical",
  "isp",
  "appliance_repair",
  "locksmith",
  "pest_control",
  "other",
] as const;

const PLANS = ["starter", "professional", "enterprise"] as const;

function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 100);
}

export default function AdminPage() {
  const [orgs, setOrgs] = useState<OrganizationRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [selected, setSelected] = useState<OrganizationRecord | null>(null);

  const [form, setForm] = useState({
    org_name: "",
    slug: "",
    industry: "hvac" as (typeof INDUSTRIES)[number],
    plan_tier: "starter" as (typeof PLANS)[number],
    business_phone: "",
    vapi_assistant_id: "",
  });

  const [settingsForm, setSettingsForm] = useState({
    system_prompt_override: "",
    first_message: "",
    issue_taxonomy: "",
    customer_segments: "",
    timezone: "America/Los_Angeles",
    business_hours_from: "08:00",
    business_hours_to: "17:00",
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setOrgs(await getOrganizations());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load organizations");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openConfigure = (org: OrganizationRecord) => {
    setSelected(org);
    const s = org.settings || {};
    const hours =
      (s.business_hours as { start?: string; end?: string } | undefined) || {};
    setSettingsForm({
      system_prompt_override: String(s.system_prompt_override || ""),
      first_message: String(s.first_message || ""),
      issue_taxonomy: Array.isArray(s.issue_taxonomy)
        ? (s.issue_taxonomy as string[]).join(", ")
        : "",
      customer_segments: Array.isArray(s.customer_segments)
        ? (s.customer_segments as string[]).join(", ")
        : "",
      timezone: String(s.timezone || "America/Los_Angeles"),
      business_hours_from: String(hours.start || "08:00"),
      business_hours_to: String(hours.end || "17:00"),
    });
  };

  const handleCreate = async () => {
    setError(null);
    const payload: OrganizationCreatePayload = {
      org_name: form.org_name,
      slug: form.slug || slugify(form.org_name),
      industry: form.industry,
      plan_tier: form.plan_tier,
      business_phone: form.business_phone || undefined,
      vapi_assistant_id: form.vapi_assistant_id || undefined,
    };
    try {
      await createOrganization(payload);
      setMessage("Organization created.");
      setShowForm(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
    }
  };

  const handleSaveSettings = async () => {
    if (!selected) return;
    const settings = {
      system_prompt_override: settingsForm.system_prompt_override || undefined,
      first_message: settingsForm.first_message || undefined,
      issue_taxonomy: settingsForm.issue_taxonomy
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
      customer_segments: settingsForm.customer_segments
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
      timezone: settingsForm.timezone,
      business_hours: {
        start: settingsForm.business_hours_from,
        end: settingsForm.business_hours_to,
      },
    };
    try {
      await updateOrganizationSettings(selected.org_id, settings);
      setMessage("Settings saved.");
      await load();
      setSelected(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    }
  };

  return (
    <div className="p-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-slate-100">
            Admin — Organizations
          </h1>
          <p className="text-sm text-gray-600 dark:text-slate-400">
            Manage all tenant organizations on the platform.
          </p>
        </div>
        <div className="flex gap-2">
          <Link
            href="/dashboard/onboarding"
            className="rounded-lg border border-indigo-600 px-4 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-50 dark:text-indigo-300"
          >
            Onboard New Client
          </Link>
          <button
            type="button"
            onClick={() => setShowForm((v) => !v)}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          >
            Add Organization
          </button>
        </div>
      </div>

      {message && (
        <p className="mb-4 text-sm text-green-700 dark:text-green-300">{message}</p>
      )}
      {error && (
        <p className="mb-4 text-sm text-red-700 dark:text-red-300">{error}</p>
      )}

      {showForm && (
        <div className="mb-6 rounded-xl border border-gray-200 bg-white p-6 dark:border-slate-700 dark:bg-slate-900">
          <h2 className="mb-4 text-lg font-semibold">New organization</h2>
          <div className="grid gap-3 md:grid-cols-2">
            <input
              className="rounded border px-3 py-2 text-sm dark:bg-slate-800"
              placeholder="Business name"
              value={form.org_name}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  org_name: e.target.value,
                  slug: f.slug || slugify(e.target.value),
                }))
              }
            />
            <input
              className="rounded border px-3 py-2 text-sm dark:bg-slate-800"
              placeholder="Slug"
              value={form.slug}
              onChange={(e) => setForm((f) => ({ ...f, slug: e.target.value }))}
            />
            <select
              className="rounded border px-3 py-2 text-sm dark:bg-slate-800"
              value={form.industry}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  industry: e.target.value as (typeof INDUSTRIES)[number],
                }))
              }
            >
              {INDUSTRIES.map((i) => (
                <option key={i} value={i}>
                  {i}
                </option>
              ))}
            </select>
            <select
              className="rounded border px-3 py-2 text-sm dark:bg-slate-800"
              value={form.plan_tier}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  plan_tier: e.target.value as (typeof PLANS)[number],
                }))
              }
            >
              {PLANS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            <input
              className="rounded border px-3 py-2 text-sm dark:bg-slate-800"
              placeholder="Business phone (Vapi inbound)"
              value={form.business_phone}
              onChange={(e) =>
                setForm((f) => ({ ...f, business_phone: e.target.value }))
              }
            />
            <input
              className="rounded border px-3 py-2 text-sm dark:bg-slate-800"
              placeholder="Vapi Assistant ID"
              value={form.vapi_assistant_id}
              onChange={(e) =>
                setForm((f) => ({ ...f, vapi_assistant_id: e.target.value }))
              }
            />
          </div>
          <button
            type="button"
            onClick={() => void handleCreate()}
            className="mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white"
          >
            Create
          </button>
        </div>
      )}

      {selected && (
        <div className="mb-6 rounded-xl border border-indigo-200 bg-indigo-50/30 p-6 dark:border-indigo-900 dark:bg-slate-900">
          <h2 className="mb-2 text-lg font-semibold">
            Configure — {selected.org_name}
          </h2>
          <div className="grid gap-3">
            <textarea
              className="rounded border px-3 py-2 text-sm dark:bg-slate-800"
              rows={4}
              placeholder="System prompt override"
              value={settingsForm.system_prompt_override}
              onChange={(e) =>
                setSettingsForm((s) => ({
                  ...s,
                  system_prompt_override: e.target.value,
                }))
              }
            />
            <input
              className="rounded border px-3 py-2 text-sm dark:bg-slate-800"
              placeholder="First message"
              value={settingsForm.first_message}
              onChange={(e) =>
                setSettingsForm((s) => ({ ...s, first_message: e.target.value }))
              }
            />
            <input
              className="rounded border px-3 py-2 text-sm dark:bg-slate-800"
              placeholder="Issue taxonomy (comma-separated)"
              value={settingsForm.issue_taxonomy}
              onChange={(e) =>
                setSettingsForm((s) => ({ ...s, issue_taxonomy: e.target.value }))
              }
            />
            <input
              className="rounded border px-3 py-2 text-sm dark:bg-slate-800"
              placeholder="Customer segments (comma-separated)"
              value={settingsForm.customer_segments}
              onChange={(e) =>
                setSettingsForm((s) => ({
                  ...s,
                  customer_segments: e.target.value,
                }))
              }
            />
            <select
              className="rounded border px-3 py-2 text-sm dark:bg-slate-800"
              value={settingsForm.timezone}
              onChange={(e) =>
                setSettingsForm((s) => ({ ...s, timezone: e.target.value }))
              }
            >
              {[
                "America/Los_Angeles",
                "America/Denver",
                "America/Chicago",
                "America/New_York",
              ].map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
            <div className="flex gap-2">
              <input
                type="time"
                className="rounded border px-3 py-2 text-sm dark:bg-slate-800"
                value={settingsForm.business_hours_from}
                onChange={(e) =>
                  setSettingsForm((s) => ({
                    ...s,
                    business_hours_from: e.target.value,
                  }))
                }
              />
              <input
                type="time"
                className="rounded border px-3 py-2 text-sm dark:bg-slate-800"
                value={settingsForm.business_hours_to}
                onChange={(e) =>
                  setSettingsForm((s) => ({
                    ...s,
                    business_hours_to: e.target.value,
                  }))
                }
              />
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <button
              type="button"
              onClick={() => void handleSaveSettings()}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white"
            >
              Save settings
            </button>
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="rounded-lg border px-4 py-2 text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white dark:border-slate-700 dark:bg-slate-900">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b bg-gray-50 dark:bg-slate-800">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Industry</th>
              <th className="px-4 py-3">Plan</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Customers</th>
              <th className="px-4 py-3">Joined</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-gray-500">
                  Loading…
                </td>
              </tr>
            ) : (
              orgs.map((org) => (
                <tr key={org.org_id} className="border-b dark:border-slate-800">
                  <td className="px-4 py-3 font-medium">{org.org_name}</td>
                  <td className="px-4 py-3">{org.industry}</td>
                  <td className="px-4 py-3">{org.plan_tier}</td>
                  <td className="px-4 py-3">
                    {org.is_active ? "Active" : "Inactive"}
                  </td>
                  <td className="px-4 py-3">{org.customer_count ?? 0}</td>
                  <td className="px-4 py-3">
                    {new Date(org.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      onClick={() => openConfigure(org)}
                      className="text-indigo-600 hover:underline dark:text-indigo-400"
                    >
                      Configure
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
