"use client";

import { Card, Text } from "@tremor/react";
import {
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

import type { CohortHeatmapResponse } from "@/types/churn";

interface Props {
  data: CohortHeatmapResponse;
}

function rateToColor(rate: number): string {
  const normalized = Math.max(0, Math.min(100, rate)) / 100;
  const red = Math.round(239 * normalized + 34 * (1 - normalized));
  const green = Math.round(68 * normalized + 197 * (1 - normalized));
  return `rgb(${red}, ${green}, 80)`;
}

export function CohortHeatmap({ data }: Props) {
  const scatterData = data.buckets.map((bucket) => ({
    bucketLabel: `${(bucket.score_range_low * 100).toFixed(0)}–${(bucket.score_range_high * 100).toFixed(0)}%`,
    scoreMid: (bucket.score_range_low + bucket.score_range_high) / 2,
    arrAtRisk: bucket.avg_arr_usd * bucket.customer_count,
    customerCount: bucket.customer_count,
    interventionSuccessRate: bucket.intervention_success_rate,
    topFeatures: bucket.top_features.join(", "),
    sample: bucket.customers_sample
      .slice(0, 3)
      .map((c) => `${c.name} (${(c.score * 100).toFixed(0)}%)`)
      .join("; "),
  }));

  if (scatterData.length === 0) {
    return (
      <Card>
        <Text>90-Day Risk Cohort Heatmap</Text>
        <p className="mt-4 text-sm text-gray-500">
          No cohort buckets available yet. Run churn scoring (batch or per-call) to
          populate score distributions.
        </p>
      </Card>
    );
  }

  return (
    <Card>
      <Text>90-Day Risk Cohort Heatmap</Text>
      <Text className="text-tremor-content-subtle text-sm">
        Scatter view per §5.1.3: score bucket (x), ARR at risk (y), dot size =
        customer count, color = intervention success rate.
      </Text>
      <p className="mt-1 text-xs text-gray-400">
        ScatterChart mapping per spec §5.1.3 (score bucket × ARR at risk).
      </p>

      <div className="mt-4 h-96">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 20, right: 30, bottom: 20, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              type="number"
              dataKey="scoreMid"
              name="Score"
              domain={[0, 1]}
              tickFormatter={(v) => `${(Number(v) * 100).toFixed(0)}%`}
              label={{ value: "Churn score bucket", position: "bottom", offset: 0 }}
            />
            <YAxis
              type="number"
              dataKey="arrAtRisk"
              name="ARR at risk"
              tickFormatter={(v) => `$${(Number(v) / 1000).toFixed(0)}k`}
              label={{ value: "ARR at risk (USD)", angle: -90, position: "insideLeft" }}
            />
            <ZAxis type="number" dataKey="customerCount" range={[80, 800]} />
            <Tooltip
              cursor={{ strokeDasharray: "3 3" }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const point = payload[0].payload as (typeof scatterData)[0];
                return (
                  <div className="rounded-md border bg-white p-3 text-xs shadow-lg">
                    <p className="font-semibold">{point.bucketLabel}</p>
                    <p>Customers: {point.customerCount}</p>
                    <p>ARR at risk: ${point.arrAtRisk.toLocaleString()}</p>
                    <p>Intervention success: {point.interventionSuccessRate.toFixed(1)}%</p>
                    {point.topFeatures && <p>Top features: {point.topFeatures}</p>}
                    {point.sample && <p className="mt-1 text-gray-500">{point.sample}</p>}
                  </div>
                );
              }}
            />
            <Scatter data={scatterData} fill="#6366f1">
              {scatterData.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={rateToColor(entry.interventionSuccessRate)}
                />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
