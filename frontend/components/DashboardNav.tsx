"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { clearAuthSession } from "@/lib/auth";
import { getOrgName } from "@/lib/config";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/customers", label: "Customers" },
  { href: "/dashboard/analytics", label: "Analytics" },
  { href: "/dashboard/knowledge", label: "Knowledge Base" },
  { href: "/dashboard/import", label: "Import" },
  { href: "/dashboard/dispatch", label: "Dispatch" },
  { href: "/dashboard/integrations", label: "Integrations" },
  { href: "/dashboard/admin", label: "Admin" },
  { href: "/dashboard/health", label: "System Health" },
];

interface DashboardNavProps {
  userEmail?: string | null;
}

export function DashboardNav({ userEmail }: DashboardNavProps) {
  const pathname = usePathname();
  const router = useRouter();
  const orgName = getOrgName();

  function handleSignOut() {
    clearAuthSession();
    router.replace("/login");
  }

  return (
    <nav className="flex h-full flex-col gap-1 p-4">
      <div className="mb-6 px-2">
        <p className="text-lg font-bold text-indigo-600 dark:text-indigo-400">{orgName}</p>
        <p className="text-xs text-gray-500 dark:text-slate-400">Churn Intelligence Dashboard</p>
      </div>
      <div className="flex flex-1 flex-col gap-1">
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
      </div>
      <div className="mt-auto border-t border-gray-200 pt-4 dark:border-slate-800">
        {userEmail && (
          <p className="mb-3 truncate px-2 text-xs text-gray-500 dark:text-slate-400" title={userEmail}>
            {userEmail}
          </p>
        )}
        <button
          type="button"
          onClick={handleSignOut}
          className="w-full rounded-lg px-3 py-2 text-left text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
        >
          Sign out
        </button>
      </div>
    </nav>
  );
}
