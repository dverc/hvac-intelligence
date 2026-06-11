const ORG_TIMEZONE = "America/Los_Angeles";

export function formatInOrgTimezone(
  isoOrDate: string | Date,
  options: Intl.DateTimeFormatOptions,
): string {
  const date = typeof isoOrDate === "string" ? new Date(isoOrDate) : isoOrDate;
  return new Intl.DateTimeFormat("en-US", {
    timeZone: ORG_TIMEZONE,
    ...options,
  }).format(date);
}

export function orgLocalDateKey(date: Date): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: ORG_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

export function orgLocalTimeParts(iso: string): { hours: number; minutes: number } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: ORG_TIMEZONE,
    hour: "numeric",
    minute: "numeric",
    hour12: false,
  }).formatToParts(new Date(iso));
  const hour = Number(parts.find((p) => p.type === "hour")?.value ?? 0);
  const minute = Number(parts.find((p) => p.type === "minute")?.value ?? 0);
  return { hours: hour, minutes: minute };
}

export { ORG_TIMEZONE };
