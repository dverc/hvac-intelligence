import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { DashboardNav } from "@/components/DashboardNav";

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
  return (
    <html lang="en">
      <body className={`${inter.className} antialiased`}>
        <div className="flex min-h-screen">
          <aside className="hidden w-56 shrink-0 border-r border-gray-200 bg-white dark:border-slate-800 dark:bg-slate-950 md:block">
            <DashboardNav />
          </aside>
          <main className="flex-1 overflow-auto">
            <div className="border-b border-gray-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-950 md:hidden">
              <p className="font-bold text-indigo-600 dark:text-indigo-400">HVAC Intelligence</p>
            </div>
            <div className="mx-auto max-w-7xl p-4 md:p-8">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
