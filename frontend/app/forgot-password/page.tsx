"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

import {
  AuthError,
  AuthFieldLabel,
  AuthHeader,
  AuthInput,
  AuthShell,
  AuthSubmitButton,
  CheckIcon,
} from "@/components/AuthShell";
import { requestPasswordReset } from "@/lib/auth";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submittedEmail, setSubmittedEmail] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await requestPasswordReset(email);
      setSubmittedEmail(email.trim());
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Unable to send reset link. Please try again.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell>
      {submittedEmail ? (
        <div className="space-y-4 text-center">
          <CheckIcon />
          <div>
            <h1 className="text-xl font-semibold text-gray-900 dark:text-slate-100">
              Check your inbox
            </h1>
            <p className="mt-2 text-sm text-gray-500 dark:text-slate-400">
              We sent a reset link to{" "}
              <span className="font-medium text-gray-700 dark:text-slate-300">
                {submittedEmail}
              </span>
            </p>
          </div>
          <Link
            href="/login"
            className="inline-block text-sm font-medium text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300"
          >
            Back to sign in
          </Link>
        </div>
      ) : (
        <>
          <AuthHeader
            title="Forgot your password?"
            subtitle="Enter your email and we'll send you a reset link"
          />

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

            <AuthSubmitButton loading={loading} label="Sending reset link">
              Send reset link
            </AuthSubmitButton>

            {error && <AuthError message={error} />}
          </form>

          <p className="mt-6 text-center text-sm text-gray-500 dark:text-slate-400">
            <Link
              href="/login"
              className="font-medium text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300"
            >
              Back to sign in
            </Link>
          </p>
        </>
      )}
    </AuthShell>
  );
}
