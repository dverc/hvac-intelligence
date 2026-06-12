"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useState } from "react";

import { ApiError, appendPortalOrgQuery, portalIdentify } from "@/lib/api";
import { getOrgName } from "@/lib/config";
import { formatPortalPhoneInput } from "@/lib/portal-format";

function PortalLandingPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const org = searchParams.get("org");
  const [phone, setPhone] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  async function handleLookup(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setNotFound(false);
    const digits = phone.replace(/\D/g, "");
    if (digits.length < 10) {
      setError("Please enter a valid 10-digit phone number.");
      return;
    }

    setLoading(true);
    try {
      const result = await portalIdentify(phone, org);
      if (result.found) {
        router.push(
          appendPortalOrgQuery(
            `/portal/appointments?phone=${encodeURIComponent(phone)}`,
            org,
          ),
        );
      } else {
        setNotFound(true);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to look up appointments.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-md">
      <div className="rounded-xl border border-gray-200 bg-white p-8 shadow-sm">
        <p className="text-center text-sm text-gray-500">{getOrgName()}</p>
        <h1 className="mt-2 text-center text-2xl font-bold text-gray-900">
          Find your appointments
        </h1>
        <p className="mt-2 text-center text-sm text-gray-500">
          Enter the phone number on your account to view upcoming service visits.
        </p>

        <form onSubmit={(e) => void handleLookup(e)} className="mt-6 space-y-4">
          <div>
            <label htmlFor="phone" className="mb-1 block text-sm font-medium text-gray-700">
              Phone number
            </label>
            <input
              id="phone"
              type="tel"
              inputMode="tel"
              autoComplete="tel"
              placeholder="(555) 555-5555"
              value={phone}
              onChange={(e) => setPhone(formatPortalPhoneInput(e.target.value))}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          {notFound && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
              <p>No account found. Would you like to request service?</p>
              <Link
                href={appendPortalOrgQuery(
                  `/portal/request?phone=${encodeURIComponent(phone)}`,
                  org,
                )}
                className="mt-2 inline-block font-medium text-indigo-700 hover:underline"
              >
                Request Service
              </Link>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {loading ? "Looking up…" : "Look Up"}
          </button>
        </form>
      </div>

      <p className="mt-6 text-center text-sm text-gray-500">
        <Link
          href={appendPortalOrgQuery("/portal/request", org)}
          className="font-medium text-indigo-600 hover:underline"
        >
          Request Service
        </Link>
      </p>
    </div>
  );
}

export default function PortalLandingPage() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <PortalLandingPageContent />
    </Suspense>
  );
}
