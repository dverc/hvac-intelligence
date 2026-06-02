"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { getOrgName } from "@/lib/config";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/customers", label: "Customers" },
  { href: "/dashboard/analytics", label: "Analytics" },
  { href: "/dashboard/knowledge", label: "Knowledge Base" },
];

export function DashboardNav() {
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
    </nav>
  );
}
