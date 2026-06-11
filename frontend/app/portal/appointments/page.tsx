"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import {
  ApiError,
  portalGetAppointments,
  portalIdentify,
  type PortalAppointment,
} from "@/lib/api";
import { formatAppointmentWindow, statusBadgeClass } from "@/lib/portal-format";

function AppointmentCard({
  appointment,
  customerId,
  muted = false,
}: {
  appointment: PortalAppointment;
  customerId: string;
  muted?: boolean;
}) {
  return (
    <div
      className={`rounded-lg border p-4 ${
        muted
          ? "border-gray-200 bg-gray-50 text-gray-600"
          : "border-gray-200 bg-white shadow-sm"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-medium text-gray-900">
            {formatAppointmentWindow(
              appointment.scheduled_window_start,
              appointment.scheduled_window_end,
            )}
          </p>
          <p className="mt-1 text-xs text-gray-500">Job #{appointment.job_number}</p>
        </div>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusBadgeClass(appointment.job_status)}`}
        >
          {appointment.job_status.replace(/_/g, " ")}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700">
          {appointment.issue_type.replace(/_/g, " ")}
        </span>
        {appointment.technician_name && (
          <span className="text-xs text-gray-500">
            Technician: {appointment.technician_name}
          </span>
        )}
      </div>
      {!muted && (
        <Link
          href={`/portal/reschedule?customer_id=${customerId}&appointment_id=${appointment.id}`}
          className="mt-4 inline-block text-sm font-medium text-indigo-600 hover:underline"
        >
          Request Reschedule
        </Link>
      )}
    </div>
  );
}

export default function PortalAppointmentsPage() {
  const searchParams = useSearchParams();
  const phone = searchParams.get("phone") ?? "";
  const customerIdParam = searchParams.get("customer_id");

  const [name, setName] = useState<string>("");
  const [customerId, setCustomerId] = useState<string>("");
  const [upcoming, setUpcoming] = useState<PortalAppointment[]>([]);
  const [past, setPast] = useState<PortalAppointment[]>([]);
  const [showPast, setShowPast] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        if (customerIdParam) {
          const data = await portalGetAppointments(customerIdParam);
          setCustomerId(data.customer_id);
          setName(data.name);
          setUpcoming(data.upcoming_appointments);
          setPast(data.past_appointments);
        } else if (phone) {
          const data = await portalIdentify(phone);
          if (!data.found || !data.customer_id) {
            setError("No account found for this phone number.");
            return;
          }
          setCustomerId(data.customer_id);
          setName(data.name ?? "");
          setUpcoming(data.upcoming_appointments);
          setPast(data.past_appointments);
        } else {
          setError("Phone number is required.");
        }
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load appointments.");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [phone, customerIdParam]);

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <span className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4 text-center">
        <p className="text-red-600">{error}</p>
        <Link href="/portal" className="text-indigo-600 hover:underline">
          ← Back to lookup
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <Link href="/portal" className="text-sm text-indigo-600 hover:underline">
          ← Back
        </Link>
        <h1 className="mt-2 text-2xl font-bold text-gray-900">
          Hello, {name}
        </h1>
        <p className="text-sm text-gray-500">Your service appointments</p>
      </div>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-gray-900">Upcoming Appointments</h2>
        {upcoming.length === 0 ? (
          <p className="rounded-lg border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500">
            No upcoming appointments
          </p>
        ) : (
          <div className="space-y-3">
            {upcoming.map((appt) => (
              <AppointmentCard
                key={appt.id}
                appointment={appt}
                customerId={customerId}
              />
            ))}
          </div>
        )}
      </section>

      <section className="space-y-4">
        <button
          type="button"
          onClick={() => setShowPast((v) => !v)}
          className="flex w-full items-center justify-between rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-left text-sm font-medium text-gray-700"
        >
          Past Appointments ({past.length})
          <span>{showPast ? "▲" : "▼"}</span>
        </button>
        {showPast && (
          <div className="space-y-3">
            {past.length === 0 ? (
              <p className="text-sm text-gray-500">No past appointments on file.</p>
            ) : (
              past.map((appt) => (
                <AppointmentCard
                  key={appt.id}
                  appointment={appt}
                  customerId={customerId}
                  muted
                />
              ))
            )}
          </div>
        )}
      </section>

      <Link
        href={`/portal/request?phone=${encodeURIComponent(phone)}`}
        className="inline-block rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-indigo-700"
      >
        Request New Service
      </Link>
    </div>
  );
}
