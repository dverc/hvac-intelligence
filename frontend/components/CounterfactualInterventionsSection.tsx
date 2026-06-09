"use client";

import { Card, Text } from "@tremor/react";
import { useEffect, useState } from "react";

import { ApiError, getCustomerCounterfactuals } from "@/lib/api";
import type { CounterfactualResponse } from "@/types/churn";

interface Props {
  customerId: string;
}

export function CounterfactualInterventionsSection({ customerId }: Props) {
  const [data, setData] = useState<CounterfactualResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const response = await getCustomerCounterfactuals(customerId);
        if (!cancelled) {
          setData(response);
        }
      } catch (err) {
        if (!cancelled) {
          const message =
            err instanceof ApiError
              ? err.message
              : "Unable to load recommended interventions";
          setError(message);
          setData(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [customerId]);

  return (
    <Card>
      <Text>Recommended Interventions</Text>
      <Text className="text-tremor-content-subtle text-sm">
        Actions that could reduce churn risk by ~20%
      </Text>

      {loading ? (
        <p className="mt-4 text-sm text-gray-500">Loading interventions…</p>
      ) : error ? (
        <p className="mt-4 text-sm text-red-600">{error}</p>
      ) : !data || data.interventions.length === 0 ? (
        <p className="mt-4 text-sm text-gray-500">
          No interventions available yet.
        </p>
      ) : (
        <div className="mt-4 space-y-3">
          {data.interventions.map((item) => (
            <div
              key={item.feature}
              className="rounded-lg border border-gray-100 px-4 py-3"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h3 className="text-sm font-semibold text-gray-900">
                  {item.friendly_name}
                </h3>
                <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-semibold text-green-800">
                  -{(item.estimated_score_reduction * 100).toFixed(0)}%
                </span>
              </div>
              <p className="mt-1 text-xs text-gray-500">
                Current: {item.current_value} → Suggested: {item.suggested_value}
              </p>
              <p className="mt-2 text-sm text-gray-700">{item.suggested_action}</p>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
