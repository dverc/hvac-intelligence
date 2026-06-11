"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { CustomerSearch } from "@/components/CustomerSearch";
import { RiskBadge } from "@/components/RiskBadge";
import { ApiError, listCustomers } from "@/lib/api";
import type { RiskTier } from "@/types/churn";
import type { CustomerListResponse } from "@/types/customer";

function CustomersPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const search = searchParams.get("q") ?? "";
  const page = Number(searchParams.get("page") ?? "1");

  const [customers, setCustomers] = useState<CustomerListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listCustomers({ search, page, limit: 50 });
      setCustomers(data);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.replace("/login");
        return;
      }
      setError(err instanceof Error ? err.message : "Failed to load customers");
    } finally {
      setLoading(false);
    }
  }, [search, page, router]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-slate-100">Customers</h1>
        <p className="text-sm text-gray-500 dark:text-slate-400">
          {customers
            ? `${customers.total} accounts · search and drill into churn timelines.`
            : "Search and drill into churn timelines."}
        </p>
      </header>

      <Suspense fallback={<div className="h-10 animate-pulse rounded bg-gray-100" />}>
        <CustomerSearch defaultValue={search} />
      </Suspense>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {error}
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        {loading ? (
          <div className="h-40 animate-pulse bg-gray-50 dark:bg-slate-800" />
        ) : (
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Name</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Phone</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Status</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Churn Risk</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {(customers?.items ?? []).map((customer) => {
                const tier = (customer.risk_tier ?? "LOW") as RiskTier;
                const customerTier = customer.customer_tier ?? "standard";
                return (
                  <tr key={customer.customer_id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Link
                          href={`/dashboard/customers/${customer.customer_id}`}
                          className="font-medium text-indigo-600 hover:underline"
                        >
                          {customer.full_name}
                        </Link>
                        {customerTier === "vip" && (
                          <span className="inline-flex items-center rounded-full bg-amber-500 px-2.5 py-0.5 text-xs font-semibold text-white">
                            VIP
                          </span>
                        )}
                        {customerTier === "preferred" && (
                          <span className="inline-flex items-center rounded-full bg-blue-600 px-2.5 py-0.5 text-xs font-semibold text-white">
                            Preferred
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-600">{customer.phone_primary}</td>
                    <td className="px-4 py-3 text-gray-600">{customer.account_status}</td>
                    <td className="px-4 py-3">
                      <RiskBadge tier={tier} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default function CustomersPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[40vh] items-center justify-center">
          <span className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
        </div>
      }
    >
      <CustomersPageContent />
    </Suspense>
  );
}
