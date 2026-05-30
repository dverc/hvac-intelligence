"use client";

import { AreaChart, BadgeDelta, Card, Metric, Text } from "@tremor/react";

import type { SavedByAIResponse } from "@/types/churn";

interface Props {
  data: SavedByAIResponse;
  priorSuccessRate?: number;
}

export function SavedByAIMetrics({ data, priorSuccessRate }: Props) {
  const chartData = data.monthly_trend.map((row) => ({
    month: row.month,
    "ARR Retained": row.arr_retained_usd,
    "Success Rate": row.success_rate,
  }));

  const delta =
    priorSuccessRate !== undefined
      ? data.intervention_success_rate - priorSuccessRate
      : undefined;

  return (
    <Card>
      <Text>Saved by AI</Text>
      <Text className="text-tremor-content-subtle text-sm">
        {new Date(data.period_start).toLocaleDateString()} –{" "}
        {new Date(data.period_end).toLocaleDateString()}
      </Text>

      <div className="mt-6 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <Text>ARR Retained</Text>
          <Metric>
            ${data.estimated_arr_retained_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </Metric>
        </div>
        <div>
          <Text>Intervention Success Rate</Text>
          <Metric>{data.intervention_success_rate.toFixed(1)}%</Metric>
          {delta !== undefined && (
            <BadgeDelta deltaType={delta >= 0 ? "increase" : "decrease"} className="mt-2">
              {delta >= 0 ? "+" : ""}
              {delta.toFixed(1)}% vs prior period
            </BadgeDelta>
          )}
        </div>
        <div>
          <Text>High-Risk Calls</Text>
          <Metric>{data.total_high_risk_calls}</Metric>
        </div>
        <div>
          <Text>Avg Score Reduction</Text>
          <Metric>{(data.avg_score_reduction * 100).toFixed(1)} pts</Metric>
        </div>
      </div>

      <div className="mt-8">
        <Text>Monthly Retention Trend</Text>
        <AreaChart
          className="mt-3 h-56"
          data={chartData}
          index="month"
          categories={["ARR Retained"]}
          colors={["indigo"]}
          valueFormatter={(value) =>
            `$${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
          }
          yAxisWidth={56}
        />
      </div>

      {data.top_intervention_types.length > 0 && (
        <div className="mt-6">
          <Text>Top Intervention Types</Text>
          <ul className="mt-2 space-y-2 text-sm">
            {data.top_intervention_types.map((item) => (
              <li
                key={item.type}
                className="flex justify-between rounded-md border border-gray-100 px-3 py-2"
              >
                <span className="font-medium">{item.type.replace(/_/g, " ")}</span>
                <span className="text-gray-500">
                  {item.count} · avg −{(item.avg_score_reduction * 100).toFixed(1)}%
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
