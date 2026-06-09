"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { DashboardNav } from "@/components/DashboardNav";
import { clearAuthSession, getAuthToken, getCurrentUser } from "@/lib/auth";
import { getApiKeyConfigError, getOrgName } from "@/lib/config";

export default function DashboardLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const apiKeyError = getApiKeyConfigError();
  const orgName = getOrgName();

  useEffect(() => {
    async function verifySession() {
      const token = getAuthToken();
      if (!token) {
        router.replace("/login");
        return;
      }

      try {
        const user = await getCurrentUser();
        setUserEmail(user.email);
        setReady(true);
      } catch {
        clearAuthSession();
        router.replace("/login");
      }
    }

    void verifySession();
  }, [router]);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--background)]">
        <span className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-56 shrink-0 border-r border-gray-200 bg-white dark:border-slate-800 dark:bg-slate-950 md:flex md:flex-col">
        <DashboardNav userEmail={userEmail} />
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
  );
}
