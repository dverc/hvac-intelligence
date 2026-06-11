export function getPublicApiKey(): string | undefined {
  const key = process.env.NEXT_PUBLIC_API_KEY?.trim();
  return key || undefined;
}

export function getOrgName(): string {
  return process.env.NEXT_PUBLIC_ORG_NAME?.trim() || "HVAC Intelligence";
}

export function getSupportPhone(): string | undefined {
  const phone = process.env.NEXT_PUBLIC_SUPPORT_PHONE?.trim();
  return phone || undefined;
}

export function getDashboardOrgId(): string {
  return (
    process.env.NEXT_PUBLIC_DASHBOARD_ORG_ID?.trim() ||
    "00000000-0000-4000-8000-000000000001"
  );
}

export function isApiKeyConfigured(): boolean {
  return Boolean(getPublicApiKey());
}

export function getApiKeyConfigError(): string | null {
  if (isApiKeyConfigured()) {
    return null;
  }
  return (
    "NEXT_PUBLIC_API_KEY is not configured. Add it to frontend/.env.local " +
    "(must match DASHBOARD_API_KEY in the backend .env)."
  );
}
