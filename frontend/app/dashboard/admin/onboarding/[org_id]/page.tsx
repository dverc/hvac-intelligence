"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  checkBackendHealth,
  createAdminOrgTechnician,
  createAdminOrgUser,
  getAdminOrganization,
  listAdminOrgTechnicians,
  provisionAdminOrganization,
  updateAdminOnboarding,
  updateAdminOrganization,
  type AdminOrganizationDetail,
  type AdminTechnicianRecord,
} from "@/lib/api";

const STEPS = [
  "Company Setup",
  "Agent Configuration",
  "Phone & Vapi Setup",
  "Team Setup",
  "Create Login",
] as const;

const TIMEZONES = [
  "America/Los_Angeles",
  "America/Denver",
  "America/Chicago",
  "America/New_York",
  "America/Phoenix",
];

const HOUR_START_OPTIONS = [6, 7, 8, 9, 10];
const HOUR_END_OPTIONS = [16, 17, 18, 19, 20, 21];
const SPECIALTIES = ["HVAC", "Electrical", "Plumbing", "General"];

export default function AdminOnboardingWizardPage() {
  const params = useParams();
  const orgId = String(params.org_id);
  const [step, setStep] = useState(1);
  const [org, setOrg] = useState<AdminOrganizationDetail | null>(null);
  const [technicians, setTechnicians] = useState<AdminTechnicianRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [healthOk, setHealthOk] = useState<boolean | null>(null);
  const [tempPassword, setTempPassword] = useState<string | null>(null);

  const [companyForm, setCompanyForm] = useState({
    display_name: "",
    address_line1: "",
    city: "",
    state: "",
    zip: "",
    phone_display: "",
    timezone: "America/Los_Angeles",
  });

  const [agentForm, setAgentForm] = useState({
    agent_greeting: "",
    business_hours_start: 8,
    business_hours_end: 18,
    outbound_enabled: false,
  });

  const [vapiForm, setVapiForm] = useState({
    vapi_assistant_id: "",
    vapi_phone_number_id: "",
    vapi_phone_number: "",
  });

  const [techForm, setTechForm] = useState({
    full_name: "",
    phone: "",
    email: "",
    specialty: "HVAC",
  });

  const [userForm, setUserForm] = useState({
    email: "",
    first_name: "",
    last_name: "",
  });

  const companyName = companyForm.display_name || org?.org_name || "Your Company";

  const greetingPreview = useMemo(() => {
    if (agentForm.agent_greeting.trim()) {
      return agentForm.agent_greeting;
    }
    return `Hi, thanks for calling ${companyName}! How can I help you today?`;
  }, [agentForm.agent_greeting, companyName]);

  function getStepValidation(currentStep: number): string | null {
    if (currentStep === 1 && !companyForm.display_name.trim()) {
      return "Company name is required before continuing.";
    }
    return null;
  }

  const stepValidation = getStepValidation(step);
  const canAdvance = stepValidation === null;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [detail, techRows] = await Promise.all([
        getAdminOrganization(orgId),
        listAdminOrgTechnicians(orgId),
      ]);
      setOrg(detail);
      setTechnicians(techRows);
      const s = detail.settings;
      if (s) {
        setStep(Math.max(1, Math.min(5, s.onboarding_step || 1)));
        setCompanyForm({
          display_name: s.display_name || detail.org_name,
          address_line1: s.address_line1 || "",
          city: s.city || "",
          state: s.state || "",
          zip: s.zip || "",
          phone_display: s.phone_display || detail.business_phone || "",
          timezone: s.timezone || "America/Los_Angeles",
        });
        setAgentForm({
          agent_greeting: s.agent_greeting || "",
          business_hours_start: s.business_hours_start,
          business_hours_end: s.business_hours_end,
          outbound_enabled: s.outbound_enabled,
        });
        setVapiForm({
          vapi_assistant_id: s.vapi_assistant_id || "",
          vapi_phone_number_id: s.vapi_phone_number_id || "",
          vapi_phone_number: s.vapi_phone_number || "",
        });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load organization");
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function persistStepData(currentStep: number) {
    if (currentStep === 1) {
      await updateAdminOrganization(orgId, {
        display_name: companyForm.display_name,
        org_name: companyForm.display_name,
        address_line1: companyForm.address_line1 || null,
        city: companyForm.city || null,
        state: companyForm.state || null,
        zip: companyForm.zip || null,
        phone_display: companyForm.phone_display || null,
        business_phone: companyForm.phone_display || null,
        timezone: companyForm.timezone,
      });
      if ((org?.settings?.onboarding_step ?? 0) === 0) {
        await provisionAdminOrganization(orgId);
      }
    } else if (currentStep === 2) {
      await updateAdminOrganization(orgId, {
        agent_greeting: agentForm.agent_greeting || null,
        business_hours_start: agentForm.business_hours_start,
        business_hours_end: agentForm.business_hours_end,
        outbound_enabled: agentForm.outbound_enabled,
      });
    } else if (currentStep === 3) {
      await updateAdminOrganization(orgId, {
        vapi_assistant_id: vapiForm.vapi_assistant_id || null,
        vapi_phone_number_id: vapiForm.vapi_phone_number_id || null,
        vapi_phone_number: vapiForm.vapi_phone_number || null,
      });
    }
  }

  async function refreshOrg() {
    const detail = await getAdminOrganization(orgId);
    setOrg(detail);
  }

  async function saveAndAdvance() {
    const validation = getStepValidation(step);
    if (validation) {
      setError(validation);
      setMessage(null);
      return;
    }
    if (step >= 5) return;

    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await persistStepData(step);
      const nextStep = step + 1;
      await updateAdminOnboarding(orgId, { onboarding_step: nextStep });
      setStep(nextStep);
      setMessage("Saved.");
      await refreshOrg();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  async function handleMarkComplete() {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await updateAdminOnboarding(orgId, {
        onboarding_completed: true,
        onboarding_step: 5,
      });
      setMessage("Onboarding marked complete.");
      await refreshOrg();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to complete onboarding");
    } finally {
      setSaving(false);
    }
  }

  async function handleAddTechnician() {
    if (!techForm.full_name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await createAdminOrgTechnician(orgId, techForm);
      setTechForm({ full_name: "", phone: "", email: "", specialty: "HVAC" });
      setTechnicians(await listAdminOrgTechnicians(orgId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to add technician");
    } finally {
      setSaving(false);
    }
  }

  async function handleCreateUser() {
    setSaving(true);
    setError(null);
    try {
      const result = await createAdminOrgUser(orgId, {
        email: userForm.email,
        first_name: userForm.first_name,
        last_name: userForm.last_name,
        role: "admin",
      });
      setTempPassword(result.temporary_password);
      setMessage("User account created.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create user");
    } finally {
      setSaving(false);
    }
  }

  async function handleTestConnection() {
    setHealthOk(null);
    const ok = await checkBackendHealth();
    setHealthOk(ok);
  }

  function copyPassword() {
    if (tempPassword) {
      void navigator.clipboard.writeText(tempPassword);
      setMessage("Password copied to clipboard.");
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <span className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header>
        <Link
          href="/dashboard/admin/organizations"
          className="text-sm text-indigo-600 hover:underline"
        >
          ← Organizations
        </Link>
        <h1 className="mt-2 text-2xl font-bold text-gray-900 dark:text-slate-100">
          Onboard {org?.settings?.display_name || org?.org_name}
        </h1>
      </header>

      <div className="flex gap-2">
        {STEPS.map((label, index) => {
          const n = index + 1;
          const done = n < step;
          const active = n === step;
          return (
            <button
              key={label}
              type="button"
              onClick={() => n <= step && setStep(n)}
              className={`flex-1 rounded-lg border px-2 py-2 text-xs font-medium ${
                active
                  ? "border-indigo-600 bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"
                  : done
                    ? "border-green-300 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-300"
                    : "border-gray-200 text-gray-400 dark:border-slate-700"
              }`}
            >
              {n}. {label}
            </button>
          );
        })}
      </div>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      {message && (
        <p className="text-sm text-green-700 dark:text-green-300">{message}</p>
      )}

      <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        {step === 1 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Company Setup</h2>
            <input
              className="w-full rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
              placeholder="Company name *"
              value={companyForm.display_name}
              onChange={(e) =>
                setCompanyForm((f) => ({ ...f, display_name: e.target.value }))
              }
            />
            <input
              className="w-full rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
              placeholder="Address line 1"
              value={companyForm.address_line1}
              onChange={(e) =>
                setCompanyForm((f) => ({ ...f, address_line1: e.target.value }))
              }
            />
            <div className="grid gap-3 md:grid-cols-3">
              <input
                className="rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
                placeholder="City"
                value={companyForm.city}
                onChange={(e) => setCompanyForm((f) => ({ ...f, city: e.target.value }))}
              />
              <input
                className="rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
                placeholder="State"
                value={companyForm.state}
                onChange={(e) => setCompanyForm((f) => ({ ...f, state: e.target.value }))}
              />
              <input
                className="rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
                placeholder="Zip"
                value={companyForm.zip}
                onChange={(e) => setCompanyForm((f) => ({ ...f, zip: e.target.value }))}
              />
            </div>
            <input
              className="w-full rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
              placeholder="Company phone"
              value={companyForm.phone_display}
              onChange={(e) =>
                setCompanyForm((f) => ({ ...f, phone_display: e.target.value }))
              }
            />
            <select
              className="w-full rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
              value={companyForm.timezone}
              onChange={(e) =>
                setCompanyForm((f) => ({ ...f, timezone: e.target.value }))
              }
            >
              {TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Agent Configuration</h2>
            <textarea
              className="w-full rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
              rows={4}
              placeholder={`Hi, thanks for calling ${companyName}! How can I help you today?`}
              value={agentForm.agent_greeting}
              onChange={(e) =>
                setAgentForm((f) => ({ ...f, agent_greeting: e.target.value }))
              }
            />
            <div className="grid gap-3 md:grid-cols-2">
              <select
                className="rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
                value={agentForm.business_hours_start}
                onChange={(e) =>
                  setAgentForm((f) => ({
                    ...f,
                    business_hours_start: parseInt(e.target.value, 10),
                  }))
                }
              >
                {HOUR_START_OPTIONS.map((h) => (
                  <option key={h} value={h}>
                    Start {h > 12 ? h - 12 : h} {h >= 12 ? "PM" : "AM"}
                  </option>
                ))}
              </select>
              <select
                className="rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
                value={agentForm.business_hours_end}
                onChange={(e) =>
                  setAgentForm((f) => ({
                    ...f,
                    business_hours_end: parseInt(e.target.value, 10),
                  }))
                }
              >
                {HOUR_END_OPTIONS.map((h) => (
                  <option key={h} value={h}>
                    End {h > 12 ? h - 12 : h} {h >= 12 ? "PM" : "AM"}
                  </option>
                ))}
              </select>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={agentForm.outbound_enabled}
                onChange={(e) =>
                  setAgentForm((f) => ({ ...f, outbound_enabled: e.target.checked }))
                }
              />
              Enable outbound calling
            </label>
            <div className="rounded-lg bg-gray-50 p-4 text-sm italic text-gray-700 dark:bg-slate-800 dark:text-slate-300">
              Preview: &ldquo;{greetingPreview}&rdquo;
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Phone &amp; Vapi Setup</h2>
            <p className="text-xs text-gray-500">
              Find these in your Vapi dashboard at dashboard.vapi.ai
            </p>
            <input
              className="w-full rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
              placeholder="Vapi Assistant ID"
              value={vapiForm.vapi_assistant_id}
              onChange={(e) =>
                setVapiForm((f) => ({ ...f, vapi_assistant_id: e.target.value }))
              }
            />
            <input
              className="w-full rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
              placeholder="Vapi Phone Number ID"
              value={vapiForm.vapi_phone_number_id}
              onChange={(e) =>
                setVapiForm((f) => ({ ...f, vapi_phone_number_id: e.target.value }))
              }
            />
            <input
              className="w-full rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
              placeholder="Inbound phone number (E.164)"
              value={vapiForm.vapi_phone_number}
              onChange={(e) =>
                setVapiForm((f) => ({ ...f, vapi_phone_number: e.target.value }))
              }
            />
            <button
              type="button"
              onClick={() => void handleTestConnection()}
              className="rounded-lg border px-4 py-2 text-sm dark:border-slate-600"
            >
              Test Connection
            </button>
            {healthOk === true && (
              <p className="text-sm text-green-600">✓ Backend is reachable</p>
            )}
            {healthOk === false && (
              <p className="text-sm text-red-600">✗ Backend unreachable</p>
            )}
          </div>
        )}

        {step === 4 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Team Setup</h2>
            <div className="grid gap-3 md:grid-cols-2">
              <input
                className="rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
                placeholder="Name *"
                value={techForm.full_name}
                onChange={(e) =>
                  setTechForm((f) => ({ ...f, full_name: e.target.value }))
                }
              />
              <select
                className="rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
                value={techForm.specialty}
                onChange={(e) =>
                  setTechForm((f) => ({ ...f, specialty: e.target.value }))
                }
              >
                {SPECIALTIES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <input
                className="rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
                placeholder="Phone"
                value={techForm.phone}
                onChange={(e) => setTechForm((f) => ({ ...f, phone: e.target.value }))}
              />
              <input
                className="rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
                placeholder="Email"
                value={techForm.email}
                onChange={(e) => setTechForm((f) => ({ ...f, email: e.target.value }))}
              />
            </div>
            <button
              type="button"
              disabled={!techForm.full_name || saving}
              onClick={() => void handleAddTechnician()}
              className="rounded-lg border px-4 py-2 text-sm dark:border-slate-600"
            >
              Add Technician
            </button>
            {technicians.length > 0 && (
              <table className="min-w-full text-left text-sm">
                <thead>
                  <tr className="border-b text-gray-500">
                    <th className="py-2 pr-4">Name</th>
                    <th className="py-2 pr-4">Phone</th>
                    <th className="py-2 pr-4">Specialty</th>
                  </tr>
                </thead>
                <tbody>
                  {technicians.map((tech) => (
                    <tr key={tech.technician_id} className="border-b dark:border-slate-800">
                      <td className="py-2 pr-4">{tech.full_name}</td>
                      <td className="py-2 pr-4">{tech.phone || "—"}</td>
                      <td className="py-2 pr-4">{tech.specialty || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {step === 5 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Create Login</h2>
            <input
              className="w-full rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
              placeholder="User email *"
              type="email"
              value={userForm.email}
              onChange={(e) => setUserForm((f) => ({ ...f, email: e.target.value }))}
            />
            <div className="grid gap-3 md:grid-cols-2">
              <input
                className="rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
                placeholder="First name"
                value={userForm.first_name}
                onChange={(e) =>
                  setUserForm((f) => ({ ...f, first_name: e.target.value }))
                }
              />
              <input
                className="rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
                placeholder="Last name"
                value={userForm.last_name}
                onChange={(e) =>
                  setUserForm((f) => ({ ...f, last_name: e.target.value }))
                }
              />
            </div>
            <button
              type="button"
              disabled={!userForm.email || saving}
              onClick={() => void handleCreateUser()}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              Create Account
            </button>
            {tempPassword && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-900 dark:bg-amber-950/40">
                <p className="text-sm font-medium text-amber-900 dark:text-amber-200">
                  Temporary password (shown once):
                </p>
                <div className="mt-2 flex items-center gap-2">
                  <code className="flex-1 rounded bg-white px-2 py-1 text-sm dark:bg-slate-900">
                    {tempPassword}
                  </code>
                  <button
                    type="button"
                    onClick={copyPassword}
                    className="rounded border px-2 py-1 text-xs"
                  >
                    Copy
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        <div className="mt-6 flex justify-between">
          <button
            type="button"
            disabled={step <= 1 || saving}
            onClick={() => setStep((s) => Math.max(1, s - 1))}
            className="rounded-lg border px-4 py-2 text-sm disabled:opacity-50 dark:border-slate-600"
          >
            Back
          </button>
          <div className="flex flex-col items-end gap-2">
            {stepValidation && step < 5 && (
              <p className="text-sm text-amber-700 dark:text-amber-300">{stepValidation}</p>
            )}
            <div className="flex gap-2">
              <button
                type="button"
                disabled={saving}
                onClick={() => void saveAndAdvance()}
                className="rounded-lg border px-4 py-2 text-sm dark:border-slate-600"
              >
                {saving ? "Saving…" : "Save"}
              </button>
              {step < 5 ? (
                canAdvance && (
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => void saveAndAdvance()}
                    className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                  >
                    Next
                  </button>
                )
              ) : (
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => void handleMarkComplete()}
                  className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                >
                  Mark as Complete
                </button>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
