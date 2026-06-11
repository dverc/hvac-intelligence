"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  listAdminOrganizations,
  type AdminOrganizationListItem,
} from "@/lib/api";

export default function AdminOnboardingIndexPage() {
  const [orgs, setOrgs] = useState<AdminOrganizationListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await listAdminOrganizations();
      setOrgs(rows.filter((org) => !org.onboarding_completed));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load onboarding queue");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-slate-100">
          Client Onboarding
        </h1>
        <p className="text-sm text-gray-500 dark:text-slate-400">
          Continue onboarding for HVAC clients in progress.
        </p>
      </header>

      {error && (
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
      )}

      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        {loading ? (
          <p className="text-sm text-gray-500">Loading…</p>
        ) : orgs.length === 0 ? (
          <div className="space-y-2">
            <p className="text-sm text-gray-500">No clients awaiting onboarding.</p>
            <Link
              href="/dashboard/admin/organizations"
              className="text-sm font-medium text-indigo-600 hover:underline"
            >
              Add a new client →
            </Link>
          </div>
        ) : (
          <ul className="divide-y dark:divide-slate-800">
            {orgs.map((org) => (
              <li
                key={org.org_id}
                className="flex items-center justify-between py-3 first:pt-0 last:pb-0"
              >
                <div>
                  <p className="font-medium text-gray-900 dark:text-slate-100">
                    {org.display_name || org.org_name}
                  </p>
                  <p className="text-xs text-gray-500">
                    Step {org.onboarding_step} of 5
                  </p>
                </div>
                <Link
                  href={`/dashboard/admin/onboarding/${org.org_id}`}
                  className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
                >
                  Continue
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
