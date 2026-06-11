"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useState } from "react";

import {
  ApiError,
  portalGetAppointments,
  portalRescheduleRequest,
  type PortalAppointment,
} from "@/lib/api";
import { formatAppointmentWindow } from "@/lib/portal-format";

const TIME_WINDOWS = [
  "Morning (8AM-12PM)",
  "Afternoon (12PM-5PM)",
  "Evening (5PM-8PM)",
] as const;

function PortalReschedulePageContent() {
  const searchParams = useSearchParams();
  const customerId = searchParams.get("customer_id") ?? "";
  const appointmentId = searchParams.get("appointment_id") ?? "";

  const [appointment, setAppointment] = useState<PortalAppointment | null>(null);
  const [preferredDate, setPreferredDate] = useState("");
  const [preferredWindow, setPreferredWindow] = useState<string>(TIME_WINDOWS[0]);
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingAppt, setLoadingAppt] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    async function loadAppointment() {
      if (!customerId || !appointmentId) {
        setError("Missing appointment information.");
        setLoadingAppt(false);
        return;
      }
      try {
        const data = await portalGetAppointments(customerId);
        const match =
          data.upcoming_appointments.find((a) => a.id === appointmentId) ??
          data.past_appointments.find((a) => a.id === appointmentId);
        if (!match) {
          setError("Appointment not found.");
        } else {
          setAppointment(match);
        }
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load appointment.");
      } finally {
        setLoadingAppt(false);
      }
    }
    void loadAppointment();
  }, [customerId, appointmentId]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!preferredDate) {
      setError("Preferred date is required.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await portalRescheduleRequest({
        customer_id: customerId,
        appointment_id: appointmentId,
        preferred_date: preferredDate,
        preferred_time_window: preferredWindow,
        reason: reason || undefined,
      });
      setSuccess(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to submit request.");
    } finally {
      setLoading(false);
    }
  }

  if (loadingAppt) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <span className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
      </div>
    );
  }

  if (success) {
    return (
      <div className="mx-auto max-w-md rounded-xl border border-green-200 bg-green-50 p-8 text-center">
        <h1 className="text-xl font-bold text-green-900">Request submitted</h1>
        <p className="mt-4 text-sm text-green-800">
          Reschedule request submitted. We&apos;ll contact you to confirm the new time.
        </p>
        <Link
          href={`/portal/appointments?customer_id=${customerId}`}
          className="mt-6 inline-block text-sm text-indigo-600 hover:underline"
        >
          ← Back to appointments
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div>
        <Link
          href={`/portal/appointments?customer_id=${customerId}`}
          className="text-sm text-indigo-600 hover:underline"
        >
          ← Back
        </Link>
        <h1 className="mt-2 text-2xl font-bold text-gray-900">Request Reschedule</h1>
      </div>

      {appointment && (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm">
          <p className="font-medium text-gray-900">Current appointment</p>
          <p className="mt-1 text-gray-600">
            {formatAppointmentWindow(
              appointment.scheduled_window_start,
              appointment.scheduled_window_end,
            )}
          </p>
          <p className="mt-1 text-gray-500">Job #{appointment.job_number}</p>
        </div>
      )}

      <form
        onSubmit={(e) => void handleSubmit(e)}
        className="space-y-4 rounded-xl border border-gray-200 bg-white p-6 shadow-sm"
      >
        <div>
          <label htmlFor="preferred_date" className="mb-1 block text-sm font-medium">
            Preferred new date *
          </label>
          <input
            id="preferred_date"
            type="date"
            required
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

        <div>
          <label htmlFor="reason" className="mb-1 block text-sm font-medium">
            Reason (optional)
          </label>
          <textarea
            id="reason"
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {loading ? "Submitting…" : "Submit Reschedule Request"}
        </button>
      </form>
    </div>
  );
}

export default function PortalReschedulePage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[40vh] items-center justify-center">
          <span className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
        </div>
      }
    >
      <PortalReschedulePageContent />
    </Suspense>
  );
}
