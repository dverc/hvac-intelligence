"use client";

import { Card, Metric, Text } from "@tremor/react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import type { ChurnDistributionResponse, RiskTier } from "@/types/churn";
import { RISK_COLORS } from "@/types/churn";

interface Props {
  data: ChurnDistributionResponse;
}

export function ChurnRiskDonut({ data }: Props) {
  const chartData = data.cohorts
    .filter((cohort) => cohort.count > 0)
    .map((cohort) => ({
      name: cohort.tier,
      value: cohort.count,
      tier: cohort.tier as RiskTier,
    }));

  const totalArrAtRisk = data.cohorts
    .filter((c) => c.tier === "HIGH" || c.tier === "CRITICAL" || c.tier === "MEDIUM")
    .reduce((sum, c) => sum + c.estimated_arr_at_risk_usd, 0);

  const highRiskAccounts =
    (data.cohorts.find((c) => c.tier === "HIGH")?.count ?? 0) +
    (data.cohorts.find((c) => c.tier === "CRITICAL")?.count ?? 0);

  const portfolioAvg =
    data.cohorts.reduce((sum, c) => sum + c.avg_score * c.count, 0) /
    (data.total_customers || 1);

  return (
    <Card className="relative">
      <Text>Churn Risk Distribution</Text>
      <Text className="text-tremor-content-subtle text-sm">
        As of {new Date(data.as_of).toLocaleString()}
      </Text>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2 h-72">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={chartData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={70}
                outerRadius={100}
                paddingAngle={2}
              >
                {chartData.map((entry) => (
                  <Cell key={entry.tier} fill={RISK_COLORS[entry.tier]} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value: number, name: string) => [
                  `${value} customers`,
                  name,
                ]}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="flex flex-col justify-center gap-4">
          <div>
            <Text>Total ARR at Risk</Text>
            <Metric>
              ${totalArrAtRisk.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </Metric>
          </div>
          <div>
            <Text>Active High-Risk Accounts</Text>
            <Metric>{highRiskAccounts}</Metric>
          </div>
          <div>
            <Text>Portfolio Avg Score</Text>
            <Metric>{(portfolioAvg * 100).toFixed(1)}%</Metric>
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-3">
        {data.cohorts.map((cohort) => (
          <div key={cohort.tier} className="flex items-center gap-2 text-sm">
            <span
              className="h-3 w-3 rounded-full"
              style={{ backgroundColor: RISK_COLORS[cohort.tier] }}
            />
            <span className="font-medium">{cohort.tier}</span>
            <span className="text-gray-500">
              {cohort.count} ({cohort.percentage}%)
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}
