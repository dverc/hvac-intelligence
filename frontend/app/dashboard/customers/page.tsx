import Link from "next/link";
import { Suspense } from "react";

import { CustomerSearch } from "@/components/CustomerSearch";
import { RiskBadge } from "@/components/RiskBadge";
import { listCustomers } from "@/lib/api";
import type { RiskTier } from "@/types/churn";

export const dynamic = "force-dynamic";

interface Props {
  searchParams: { q?: string; page?: string };
}

export default async function CustomersPage({ searchParams }: Props) {
  const search = searchParams.q ?? "";
  const page = Number(searchParams.page ?? "1");

  const customers = await listCustomers({ search, page, limit: 50 });

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-slate-100">Customers</h1>
        <p className="text-sm text-gray-500 dark:text-slate-400">
          {customers.total} accounts · search and drill into churn timelines.
        </p>
      </header>

      <Suspense fallback={<div className="h-10 animate-pulse rounded bg-gray-100" />}>
        <CustomerSearch defaultValue={search} />
      </Suspense>

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
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
            {customers.items.map((customer) => {
              const tier = (customer.risk_tier ?? "LOW") as RiskTier;
              return (
                <tr key={customer.customer_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <Link
                      href={`/dashboard/customers/${customer.customer_id}`}
                      className="font-medium text-indigo-600 hover:underline"
                    >
                      {customer.full_name}
                    </Link>
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
      </div>
    </div>
  );
}
