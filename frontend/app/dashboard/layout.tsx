"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { LogoutIcon } from "@/components/AuthShell";
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
  const [signOutModalOpen, setSignOutModalOpen] = useState(false);
  const apiKeyError = getApiKeyConfigError();
  const orgName = getOrgName();

  useEffect(() => {
    if (!signOutModalOpen) {
      return;
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setSignOutModalOpen(false);
      }
    }

    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [signOutModalOpen]);

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

  function handleSignOut() {
    clearAuthSession();
    router.replace("/login");
  }

  function openSignOutModal() {
    setSignOutModalOpen(true);
  }

  function closeSignOutModal() {
    setSignOutModalOpen(false);
  }

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-100 dark:bg-slate-950">
        <span className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-56 shrink-0 flex-col border-r border-gray-200 bg-white dark:border-slate-800 dark:bg-slate-950 md:flex">
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
          <DashboardNav />
        </div>
        <div className="border-t border-gray-200 p-4 dark:border-slate-800">
          {userEmail && (
            <p
              className="mb-3 truncate px-1 text-xs text-gray-500 dark:text-slate-400"
              title={userEmail}
            >
              {userEmail}
            </p>
          )}
          <button
            type="button"
            onClick={openSignOutModal}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
          >
            <LogoutIcon />
            Sign out
          </button>
        </div>
      </aside>
      {signOutModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
          onClick={closeSignOutModal}
          role="presentation"
        >
          <div
            className="w-full max-w-[320px] rounded-xl bg-white p-6 shadow-lg dark:bg-slate-900"
            role="dialog"
            aria-modal="true"
            aria-labelledby="sign-out-title"
            onClick={(event) => event.stopPropagation()}
          >
            <h2
              id="sign-out-title"
              className="text-lg font-bold text-gray-900 dark:text-slate-100"
            >
              Sign out?
            </h2>
            <p className="mt-2 text-sm text-gray-500 dark:text-slate-400">
              You&apos;ll need to sign back in to access your dashboard.
            </p>
            <div className="mt-6 flex gap-3">
              <button
                type="button"
                onClick={closeSignOutModal}
                className="flex-1 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                Stay logged in
              </button>
              <button
                type="button"
                onClick={handleSignOut}
                className="flex-1 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700"
              >
                Sign out
              </button>
            </div>
          </div>
        </div>
      )}
      <main className="flex-1 overflow-auto bg-slate-100 dark:bg-slate-950">
        <div className="border-b border-gray-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-950 md:hidden">
          <p className="font-bold text-indigo-600 dark:text-indigo-400">{orgName}</p>
        </div>
        <div className="mx-auto max-w-7xl p-4 md:p-8">
          {apiKeyError ? (
            <div
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300"
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
