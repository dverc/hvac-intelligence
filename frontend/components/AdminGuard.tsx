"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getStoredUserRole } from "@/lib/auth";

export function AdminGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [authorized, setAuthorized] = useState(false);

  useEffect(() => {
    const role = getStoredUserRole();
    if (role === "admin") {
      setAuthorized(true);
      return;
    }
    router.replace("/dashboard");
  }, [router]);

  if (!authorized) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <span className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
      </div>
    );
  }

  return <>{children}</>;
}
