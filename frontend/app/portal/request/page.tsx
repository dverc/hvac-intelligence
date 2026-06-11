"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";

import { ApiError, portalRequestService } from "@/lib/api";
import { formatPortalPhoneInput } from "@/lib/portal-format";

const ISSUE_TYPES = [
  "AC Not Cooling",
  "AC Not Heating",
  "No Heat",
  "Maintenance",
  "Emergency",
  "Other",
] as const;

const TIME_WINDOWS = [
  "Morning (8AM-12PM)",
  "Afternoon (12PM-5PM)",
  "Evening (5PM-8PM)",
] as const;

export default function PortalRequestPage() {
  const searchParams = useSearchParams();
  const [phone, setPhone] = useState(searchParams.get("phone") ?? "");
  const [name, setName] = useState("");
  const [issueType, setIssueType] = useState<string>(ISSUE_TYPES[0]);
  const [description, setDescription] = useState("");
  const [preferredDate, setPreferredDate] = useState("");
  const [preferredWindow, setPreferredWindow] = useState<string>(TIME_WINDOWS[0]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ticketNumber, setTicketNumber] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const digits = phone.replace(/\D/g, "");
    if (digits.length < 10) {
      setError("Phone number is required.");
      return;
    }

    setLoading(true);
    try {
      const result = await portalRequestService({
        phone,
        name: name || undefined,
        issue_type: issueType,
        description: description || undefined,
        preferred_date: preferredDate || undefined,
        preferred_time_window: preferredWindow,
      });
      setTicketNumber(result.ticket_number);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to submit request.");
    } finally {
      setLoading(false);
    }
  }

  if (ticketNumber) {
    return (
      <div className="mx-auto max-w-md rounded-xl border border-green-200 bg-green-50 p-8 text-center">
        <h1 className="text-xl font-bold text-green-900">Request received</h1>
        <p className="mt-2 text-sm text-green-800">
          Your ticket number is <strong>{ticketNumber}</strong>
        </p>
        <p className="mt-4 text-sm text-green-800">
          We&apos;ll contact you within 2 hours during business hours.
        </p>
        <Link href="/portal" className="mt-6 inline-block text-sm text-indigo-600 hover:underline">
          ← Back to portal
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div>
        <Link href="/portal" className="text-sm text-indigo-600 hover:underline">
          ← Back
        </Link>
        <h1 className="mt-2 text-2xl font-bold text-gray-900">Request Service</h1>
        <p className="text-sm text-gray-500">
          Tell us about your issue and we&apos;ll follow up to schedule a visit.
        </p>
      </div>

      <form
        onSubmit={(e) => void handleSubmit(e)}
        className="space-y-4 rounded-xl border border-gray-200 bg-white p-6 shadow-sm"
      >
        <div>
          <label htmlFor="issue_type" className="mb-1 block text-sm font-medium">
            Issue type
          </label>
          <select
            id="issue_type"
            value={issueType}
            onChange={(e) => setIssueType(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            {ISSUE_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="description" className="mb-1 block text-sm font-medium">
            Description
          </label>
          <textarea
            id="description"
            rows={4}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            placeholder="Describe the problem..."
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="preferred_date" className="mb-1 block text-sm font-medium">
              Preferred date
            </label>
            <input
              id="preferred_date"
              type="date"
              value={preferredDate}
              onChange={(e) => setPreferredDate(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label htmlFor="preferred_window" className="mb-1 block text-sm font-medium">
              Preferred time window
            </label>
            <select
              id="preferred_window"
              value={preferredWindow}
              onChange={(e) => setPreferredWindow(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            >
              {TIME_WINDOWS.map((window) => (
                <option key={window} value={window}>
                  {window}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label htmlFor="phone" className="mb-1 block text-sm font-medium">
            Phone number *
          </label>
          <input
            id="phone"
            type="tel"
            required
            value={phone}
            onChange={(e) => setPhone(formatPortalPhoneInput(e.target.value))}
            placeholder="(555) 555-5555"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
        </div>

        <div>
          <label htmlFor="name" className="mb-1 block text-sm font-medium">
            Name
          </label>
          <input
            id="name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {loading ? "Submitting…" : "Submit Request"}
        </button>
      </form>
    </div>
  );
}
