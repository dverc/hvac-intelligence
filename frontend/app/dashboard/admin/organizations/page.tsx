"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import {
  ApiError,
  createAdminOrganization,
  listAdminOrganizations,
  type AdminOrganizationListItem,
} from "@/lib/api";

function statusBadgeClass(status: string): string {
  switch (status) {
    case "ACTIVE":
      return "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300";
    case "TRIAL":
      return "bg-yellow-100 text-yellow-800 dark:bg-yellow-950 dark:text-yellow-300";
    default:
      return "bg-gray-100 text-gray-700 dark:bg-slate-800 dark:text-slate-300";
  }
}

function AdminOrganizationsPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [orgs, setOrgs] = useState<AdminOrganizationListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    company_name: "",
    admin_email: "",
    admin_first_name: "",
    admin_last_name: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setOrgs(await listAdminOrganizations());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load organizations");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (searchParams.get("action") === "new") {
      setModalOpen(true);
    }
  }, [searchParams]);

  async function handleCreate() {
    setCreating(true);
    setError(null);
    try {
      const result = await createAdminOrganization(form);
      setModalOpen(false);
      setForm({
        company_name: "",
        admin_email: "",
        admin_first_name: "",
        admin_last_name: "",
      });
      router.push(`/dashboard/admin/onboarding/${result.org_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create organization");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-slate-100">
            Client Organizations
          </h1>
          <p className="text-sm text-gray-500 dark:text-slate-400">
            Manage HVAC company tenants and onboarding progress.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        >
          Add New Client
        </button>
      </header>

      {error && (
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
      )}

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900">
        {loading ? (
          <p className="p-6 text-sm text-gray-500">Loading…</p>
        ) : orgs.length === 0 ? (
          <p className="p-6 text-sm text-gray-500">No organizations yet.</p>
        ) : (
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-gray-200 bg-gray-50 dark:border-slate-700 dark:bg-slate-800">
              <tr>
                <th className="px-4 py-3 font-medium text-gray-600">Company Name</th>
                <th className="px-4 py-3 font-medium text-gray-600">Status</th>
                <th className="px-4 py-3 font-medium text-gray-600">Users</th>
                <th className="px-4 py-3 font-medium text-gray-600">Technicians</th>
                <th className="px-4 py-3 font-medium text-gray-600">Onboarding</th>
                <th className="px-4 py-3 font-medium text-gray-600">Actions</th>
              </tr>
            </thead>
            <tbody>
              {orgs.map((org) => (
                <tr key={org.org_id} className="border-b dark:border-slate-800">
                  <td className="px-4 py-3 font-medium">
                    {org.display_name || org.org_name}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2 py-1 text-xs font-semibold ${statusBadgeClass(org.status)}`}
                    >
                      {org.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">{org.user_count}</td>
                  <td className="px-4 py-3">{org.technician_count}</td>
                  <td className="px-4 py-3">
                    {org.onboarding_completed ? (
                      <span className="rounded-full bg-green-100 px-2 py-1 text-xs font-semibold text-green-800 dark:bg-green-950 dark:text-green-300">
                        Complete
                      </span>
                    ) : (
                      <div className="flex items-center gap-2">
                        <div className="h-2 w-24 overflow-hidden rounded-full bg-gray-200 dark:bg-slate-700">
                          <div
                            className="h-full bg-indigo-600"
                            style={{ width: `${(org.onboarding_step / 5) * 100}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-500">
                          {org.onboarding_step}/5
                        </span>
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2">
                      <Link
                        href={`/dashboard/admin/onboarding/${org.org_id}`}
                        className="text-indigo-600 hover:underline"
                      >
                        {org.onboarding_completed ? "Edit" : "Onboard"}
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-lg dark:bg-slate-900">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100">
              Add New Client
            </h2>
            <div className="mt-4 space-y-3">
              <input
                className="w-full rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
                placeholder="Company name *"
                value={form.company_name}
                onChange={(e) =>
                  setForm((f) => ({ ...f, company_name: e.target.value }))
                }
              />
              <input
                className="w-full rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
                placeholder="Admin email *"
                type="email"
                value={form.admin_email}
                onChange={(e) =>
                  setForm((f) => ({ ...f, admin_email: e.target.value }))
                }
              />
              <div className="flex gap-2">
                <input
                  className="w-full rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
                  placeholder="First name"
                  value={form.admin_first_name}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, admin_first_name: e.target.value }))
                  }
                />
                <input
                  className="w-full rounded-lg border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
                  placeholder="Last name"
                  value={form.admin_last_name}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, admin_last_name: e.target.value }))
                  }
                />
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setModalOpen(false)}
                className="rounded-lg border px-4 py-2 text-sm dark:border-slate-600"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!form.company_name || !form.admin_email || creating}
                onClick={() => void handleCreate()}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {creating ? "Creating…" : "Create & Onboard"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function AdminOrganizationsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[40vh] items-center justify-center">
          <span className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
        </div>
      }
    >
      <AdminOrganizationsPageContent />
    </Suspense>
  );
}
