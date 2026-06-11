import { getApiBaseUrl } from "@/lib/api";

export const TOKEN_KEY = "hvac_token";
export const EMAIL_KEY = "hvac_user_email";
export const ROLE_KEY = "hvac_user_role";
export const ORG_ID_KEY = "hvac_org_id";

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user_id: string;
  email: string;
  role: string;
  org_id: string;
}

export interface UserProfile {
  user_id: string;
  email: string;
  role: string;
  org_id: string;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export class AuthError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "AuthError";
  }
}

export function getAuthToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUserEmail(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return localStorage.getItem(EMAIL_KEY);
}

export function getStoredUserRole(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return localStorage.getItem(ROLE_KEY);
}

export function storeAuthSession(login: LoginResponse): void {
  localStorage.setItem(TOKEN_KEY, login.access_token);
  localStorage.setItem(EMAIL_KEY, login.email);
  localStorage.setItem(ROLE_KEY, login.role);
  localStorage.setItem(ORG_ID_KEY, login.org_id);
}

export function clearAuthSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EMAIL_KEY);
  localStorage.removeItem(ROLE_KEY);
  localStorage.removeItem(ORG_ID_KEY);
}

function parseErrorMessage(body: string): string {
  try {
    const parsed = JSON.parse(body) as { detail?: string | { msg?: string }[] };
    if (typeof parsed.detail === "string") {
      return parsed.detail;
    }
    if (Array.isArray(parsed.detail) && parsed.detail[0]?.msg) {
      return parsed.detail[0].msg;
    }
  } catch {
    // fall through
  }
  return body || "Request failed";
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const form = new URLSearchParams();
  form.set("username", email.trim());
  form.set("password", password);

  const response = await fetch(`${getApiBaseUrl()}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form.toString(),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new AuthError(response.status, parseErrorMessage(body));
  }

  return response.json() as Promise<LoginResponse>;
}

export async function getCurrentUser(): Promise<UserProfile> {
  const token = getAuthToken();
  if (!token) {
    throw new AuthError(401, "Not authenticated");
  }

  const response = await fetch(`${getApiBaseUrl()}/api/v1/auth/me`, {
    cache: "no-store",
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const body = await response.text();
    throw new AuthError(response.status, parseErrorMessage(body));
  }

  return response.json() as Promise<UserProfile>;
}

export async function requestPasswordReset(email: string): Promise<{ message: string }> {
  const response = await fetch(`${getApiBaseUrl()}/api/v1/auth/forgot-password`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ email: email.trim() }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new AuthError(response.status, parseErrorMessage(body));
  }

  return response.json() as Promise<{ message: string }>;
}

export async function resetPassword(
  token: string,
  newPassword: string,
): Promise<{ message: string }> {
  const response = await fetch(`${getApiBaseUrl()}/api/v1/auth/reset-password`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ token, new_password: newPassword }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new AuthError(response.status, parseErrorMessage(body));
  }

  return response.json() as Promise<{ message: string }>;
}
