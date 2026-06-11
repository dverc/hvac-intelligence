const PORTAL_TZ_FALLBACK = "America/Los_Angeles";

export function formatPortalPhoneInput(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 10);
  if (digits.length <= 3) return digits;
  if (digits.length <= 6) {
    return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
  }
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
}

export function formatAppointmentWindow(
  startIso: string | null,
  endIso: string | null,
  timezone?: string,
): string {
  const tz = timezone ?? PORTAL_TZ_FALLBACK;
  if (!startIso) return "Time to be confirmed";
  const start = new Date(startIso);
  const end = endIso ? new Date(endIso) : null;
  const day = new Intl.DateTimeFormat("en-US", {
    timeZone: tz,
    weekday: "long",
    month: "long",
    day: "numeric",
  }).format(start);
  const startTime = new Intl.DateTimeFormat("en-US", {
    timeZone: tz,
    hour: "numeric",
    minute: "2-digit",
  }).format(start);
  if (!end) return `${day} · ${startTime}`;
  const endTime = new Intl.DateTimeFormat("en-US", {
    timeZone: tz,
    hour: "numeric",
    minute: "2-digit",
  }).format(end);
  return `${day} · ${startTime} – ${endTime}`;
}

export function statusBadgeClass(status: string): string {
  const normalized = status.toUpperCase();
  if (normalized === "SCHEDULED" || normalized === "IN_PROGRESS") {
    return "bg-blue-100 text-blue-800";
  }
  if (normalized === "COMPLETED") {
    return "bg-green-100 text-green-800";
  }
  if (normalized === "CANCELLED" || normalized === "RESCHEDULED") {
    return "bg-gray-100 text-gray-600";
  }
  return "bg-gray-100 text-gray-700";
}
