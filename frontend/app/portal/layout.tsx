import Link from "next/link";
import type { ReactNode } from "react";

import { getOrgName, getSupportPhone } from "@/lib/config";

export default function PortalLayout({ children }: { children: ReactNode }) {
  const orgName = getOrgName();
  const supportPhone = getSupportPhone();

  return (
    <div className="flex min-h-screen flex-col bg-white text-gray-900">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-4">
          <Link href="/portal" className="flex flex-col">
            <span className="text-lg font-bold text-indigo-700">{orgName}</span>
            <span className="text-xs text-gray-500">Customer Portal</span>
          </Link>
        </div>
      </header>

      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8">{children}</main>

      <footer className="border-t border-gray-200 bg-gray-50 py-6 text-center text-sm text-gray-500">
        <p>Powered by HVAC Intelligence</p>
        {supportPhone && (
          <p className="mt-1">
            Support:{" "}
            <a href={`tel:${supportPhone}`} className="text-indigo-600 hover:underline">
              {supportPhone}
            </a>
          </p>
        )}
      </footer>
    </div>
  );
}
