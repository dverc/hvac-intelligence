"use client";

import { Card, Text } from "@tremor/react";
import { useEffect, useMemo, useState } from "react";
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

const INCREASES_RISK_COLOR = "#ef4444";
const DECREASES_RISK_COLOR = "#22c55e";

const EMPTY_SHAP_MESSAGE =
  "Risk factor analysis will populate after the model is trained on real customer data. Current score is based on rule-based assessment.";

function truncateLabel(label: string, max = 20): string {
  if (label.length <= max) {
    return label;
  }
  return `${label.slice(0, max - 1)}…`;
}

function directionColor(direction: "INCREASES_RISK" | "DECREASES_RISK"): string {
  return direction === "INCREASES_RISK" ? INCREASES_RISK_COLOR : DECREASES_RISK_COLOR;
}

function directionLabel(direction: "INCREASES_RISK" | "DECREASES_RISK"): string {
  return direction === "INCREASES_RISK" ? "Increases Risk" : "Decreases Risk";
}

interface ChartDatum {
  name: string;
  fullName: string;
  shap_value: number;
  direction: "INCREASES_RISK" | "DECREASES_RISK";
  fill: string;
}

function ShapTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: ChartDatum }>;
}) {
  if (!active || !payload?.length) {
    return null;
  }

  const entry = payload[0].payload;

  return (
    <div className="rounded border border-gray-200 bg-white p-3 text-sm shadow-md">
      <p className="font-medium text-gray-900">{entry.fullName}</p>
      <p className="mt-1 text-gray-700">SHAP value: {entry.shap_value.toFixed(4)}</p>
      <p className="mt-1 font-medium" style={{ color: entry.fill }}>
        {directionLabel(entry.direction)}
      </p>
    </div>
  );
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

  const chartData: ChartDatum[] = useMemo(
    () =>
      data?.features.map((feature) => ({
        name: truncateLabel(feature.friendly_name),
        fullName: feature.friendly_name,
        shap_value: feature.shap_value,
        direction: feature.direction,
        fill: directionColor(feature.direction),
      })) ?? [],
    [data],
  );

  const hasMeaningfulShap =
    chartData.length > 0 && chartData.some((feature) => feature.shap_value !== 0);

  const yDomain = useMemo(() => {
    if (!hasMeaningfulShap) {
      return [0, 1] as [number, number];
    }

    const values = chartData.map((feature) => feature.shap_value);
    const minValue = Math.min(...values, 0);
    const maxValue = Math.max(...values, 0);
    const span = maxValue - minValue;
    const padding = span > 0 ? span * 0.1 : 0.01;

    return [minValue - padding, maxValue + padding] as [number, number];
  }, [chartData, hasMeaningfulShap]);

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
      ) : !data || !hasMeaningfulShap ? (
        <p className="mt-4 text-sm text-gray-500">{EMPTY_SHAP_MESSAGE}</p>
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
              <YAxis tick={{ fontSize: 11 }} domain={yDomain} />
              <Tooltip content={<ShapTooltip />} />
              <ReferenceLine y={0} stroke="#9ca3af" />
              <Bar dataKey="shap_value" radius={[4, 4, 0, 0]}>
                {chartData.map((entry) => (
                  <Cell key={entry.fullName} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}
