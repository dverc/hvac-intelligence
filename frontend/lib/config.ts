export function getPublicApiKey(): string | undefined {
  const key = process.env.NEXT_PUBLIC_API_KEY?.trim();
  return key || undefined;
}

export function getOrgName(): string {
  return process.env.NEXT_PUBLIC_ORG_NAME?.trim() || "HVAC Intelligence";
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
