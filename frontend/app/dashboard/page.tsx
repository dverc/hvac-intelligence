"use client";

import { useCallback, useEffect, useState } from "react";

import { ChurnRiskDonut } from "@/components/ChurnRiskDonut";
import { LiveCallFeed } from "@/components/LiveCallFeed";
import { SavedByAIMetrics } from "@/components/SavedByAIMetrics";
import {
  ApiError,
  defaultAnalyticsRange,
  getChurnProbabilityDistribution,
  getSavedByAI,
} from "@/lib/api";
import type { ChurnDistributionResponse, SavedByAIResponse } from "@/types/churn";

export default function DashboardPage() {
  const [distribution, setDistribution] = useState<ChurnDistributionResponse | null>(
    null,
  );
  const [savedByAI, setSavedByAI] = useState<SavedByAIResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const { start, end } = defaultAnalyticsRange();
    try {
      const [distributionData, savedData] = await Promise.all([
        getChurnProbabilityDistribution(),
        getSavedByAI(start, end),
      ]);
      setDistribution(distributionData);
      setSavedByAI(savedData);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Failed to load dashboard analytics";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <span className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
      </div>
    );
  }

  if (error || !distribution || !savedByAI) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
        {error ?? "Failed to load dashboard data"}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-slate-100">
          Operations Overview
        </h1>
        <p className="text-sm text-gray-500 dark:text-slate-400">
          Portfolio churn risk, AI retention impact, and live call activity.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <ChurnRiskDonut data={distribution} />
        </div>
        <div className="xl:col-span-1">
          <LiveCallFeed />
        </div>
      </div>

      <SavedByAIMetrics data={savedByAI} />
    </div>
  );
}
