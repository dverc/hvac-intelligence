"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { getOrgName } from "@/lib/config";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/customers", label: "Customers" },
  { href: "/dashboard/analytics", label: "Analytics" },
  { href: "/dashboard/knowledge", label: "Knowledge Base" },
  { href: "/dashboard/import", label: "Import" },
  { href: "/dashboard/dispatch", label: "Dispatch" },
  { href: "/dashboard/outbound", label: "Outbound" },
  { href: "/dashboard/integrations", label: "Integrations" },
  { href: "/dashboard/admin", label: "Admin" },
  { href: "/dashboard/health", label: "System Health" },
];

const ADMIN_NAV_ITEMS = [
  { href: "/dashboard/admin/organizations", label: "Organizations" },
  { href: "/dashboard/admin/onboarding", label: "Onboarding" },
];

export function DashboardNav({ isAdmin = false }: { isAdmin?: boolean }) {
  const pathname = usePathname();
  const orgName = getOrgName();

  return (
    <nav className="flex flex-col gap-1 p-4">
      <div className="mb-6 px-2">
        <p className="text-lg font-bold text-indigo-600 dark:text-indigo-400">{orgName}</p>
        <p className="text-xs text-gray-500 dark:text-slate-400">Churn Intelligence Dashboard</p>
      </div>
      {NAV_ITEMS.map((item) => {
        const active =
          pathname === item.href ||
          (item.href !== "/dashboard" && pathname.startsWith(item.href));
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              active
                ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"
                : "text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
      {isAdmin && (
        <div className="mt-4 border-t border-gray-200 pt-4 dark:border-slate-800">
          <p className="mb-2 px-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
            Admin
          </p>
          {ADMIN_NAV_ITEMS.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`block rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  active
                    ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"
                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      )}
    </nav>
  );
}
