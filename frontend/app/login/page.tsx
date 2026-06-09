"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import {
  AuthError,
  AuthFieldLabel,
  AuthHeader,
  AuthInput,
  AuthShell,
  AuthSubmitButton,
  EyeIcon,
} from "@/components/AuthShell";
import { login, storeAuthSession } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const result = await login(email, password);
      storeAuthSession(result);
      router.replace("/dashboard");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Unable to sign in. Please try again.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell>
      <AuthHeader title="HVAC Intelligence" subtitle="Sign in to your account" />

      <form onSubmit={(event) => void handleSubmit(event)} className="space-y-4">
        <div>
          <AuthFieldLabel htmlFor="email">Email</AuthFieldLabel>
          <AuthInput
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@company.com"
          />
        </div>

        <div>
          <AuthFieldLabel htmlFor="password">Password</AuthFieldLabel>
          <div className="relative">
            <AuthInput
              id="password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="pr-10"
              placeholder="Enter your password"
            />
            <button
              type="button"
              onClick={() => setShowPassword((value) => !value)}
              className="absolute inset-y-0 right-0 flex items-center px-3 text-gray-500 hover:text-gray-700 dark:text-slate-400 dark:hover:text-slate-200"
              aria-label={showPassword ? "Hide password" : "Show password"}
            >
              <EyeIcon open={showPassword} />
            </button>
          </div>
        </div>

        <AuthSubmitButton loading={loading} label="Signing in">
          Sign in
        </AuthSubmitButton>

        {error && <AuthError message={error} />}
      </form>

      <p className="mt-6 text-center text-sm text-gray-500 dark:text-slate-400">
        <Link
          href="/forgot-password"
          className="font-medium text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300"
        >
          Forgot password?
        </Link>
      </p>
    </AuthShell>
  );
}
