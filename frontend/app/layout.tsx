import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { DashboardNav } from "@/components/DashboardNav";

import { getApiKeyConfigError, getOrgName } from "@/lib/config";

import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "HVAC Intelligence — Churn Dashboard",
  description: "90-day predictive churn and voice retention telemetry",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const apiKeyError = getApiKeyConfigError();
  const orgName = getOrgName();

  return (
    <html lang="en">
      <body className={`${inter.className} antialiased`}>
        <div className="flex min-h-screen">
          <aside className="hidden w-56 shrink-0 border-r border-gray-200 bg-white dark:border-slate-800 dark:bg-slate-950 md:block">
            <DashboardNav />
          </aside>
          <main className="flex-1 overflow-auto">
            <div className="border-b border-gray-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-950 md:hidden">
              <p className="font-bold text-indigo-600 dark:text-indigo-400">{orgName}</p>
            </div>
            <div className="mx-auto max-w-7xl p-4 md:p-8">
              {apiKeyError ? (
                <div
                  role="alert"
                  className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-800"
                >
                  <p className="font-semibold">API configuration required</p>
                  <p className="mt-2 text-sm">{apiKeyError}</p>
                </div>
              ) : (
                children
              )}
            </div>
          </main>
        </div>
      </body>
    </html>
  );
}
