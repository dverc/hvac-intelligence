"use client";

import { Card, Text } from "@tremor/react";
import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ApiError, getCustomerShapExplanation } from "@/lib/api";
import type { ShapExplanationResponse } from "@/types/churn";

interface Props {
  customerId: string;
}

function truncateLabel(label: string, max = 20): string {
  if (label.length <= max) {
    return label;
  }
  return `${label.slice(0, max - 1)}…`;
}

export function ShapWaterfallSection({ customerId }: Props) {
  const [data, setData] = useState<ShapExplanationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const response = await getCustomerShapExplanation(customerId);
        if (!cancelled) {
          setData(response);
        }
      } catch (err) {
        if (!cancelled) {
          const message =
            err instanceof ApiError
              ? err.message
              : "Unable to load SHAP explanation";
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

  const chartData =
    data?.features.map((feature) => ({
      name: truncateLabel(feature.friendly_name),
      shap_value: feature.shap_value,
      fill: feature.shap_value >= 0 ? "#f97316" : "#22c55e",
    })) ?? [];

  return (
    <Card>
      <Text>Risk Factor Analysis</Text>
      <Text className="text-tremor-content-subtle text-sm">
        How each factor contributes to churn risk
      </Text>

      {loading ? (
        <p className="mt-4 text-sm text-gray-500">Loading SHAP analysis…</p>
      ) : error ? (
        <p className="mt-4 text-sm text-red-600">{error}</p>
      ) : !data || chartData.length === 0 ? (
        <p className="mt-4 text-sm text-gray-500">
          No SHAP data available yet — scores will populate after model training.
        </p>
      ) : (
        <div className="mt-4">
          <p className="mb-2 text-xs text-gray-500">
            Current risk {(data.churn_probability * 100).toFixed(1)}% · Baseline{" "}
            {(data.baseline_probability * 100).toFixed(1)}%
          </p>
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 48 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis
                dataKey="name"
                tick={{ fontSize: 10 }}
                interval={0}
                angle={-30}
                textAnchor="end"
                height={70}
              />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value: number) => [value.toFixed(4), "SHAP value"]}
              />
              <ReferenceLine y={0} stroke="#9ca3af" />
              <Bar dataKey="shap_value" radius={[4, 4, 0, 0]}>
                {chartData.map((entry) => (
                  <Cell key={entry.name} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}
