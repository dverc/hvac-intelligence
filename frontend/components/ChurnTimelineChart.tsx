"use client";

import { format, parseISO } from "date-fns";
import {
  CartesianGrid,
  Label,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ChurnTimelinePoint } from "@/types/churn";
import { RISK_COLORS } from "@/types/churn";

interface Props {
  data: ChurnTimelinePoint[];
  savedByAI: boolean;
}

export function ChurnTimelineChart({ data, savedByAI }: Props) {
  const interventionPoints = data.filter(
    (point) => point.event?.type === "INTERVENTION_APPLIED",
  );

  const showSavedBadge =
    savedByAI &&
    data.length > 0 &&
    data[data.length - 1].churn_probability - data[0].churn_probability <= -0.15;

  return (
    <div className="relative">
      {showSavedBadge && (
        <div className="absolute top-2 right-2 z-10 rounded-full border border-green-300 bg-green-100 px-2 py-1 text-xs font-bold text-green-800">
          ✓ SAVED BY AI
        </div>
      )}
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis
            dataKey="timestamp"
            tickFormatter={(value) => format(parseISO(value), "MMM d")}
            tick={{ fontSize: 11 }}
          />
          <YAxis
            domain={[0, 1]}
            tickFormatter={(value) => `${(Number(value) * 100).toFixed(0)}%`}
            tick={{ fontSize: 11 }}
          />
          <Tooltip
            formatter={(value: number) => [
              `${(value * 100).toFixed(1)}%`,
              "Churn Probability",
            ]}
            labelFormatter={(label) =>
              format(parseISO(String(label)), "MMM d, yyyy HH:mm")
            }
          />
          <ReferenceLine y={0.6} stroke={RISK_COLORS.HIGH} strokeDasharray="4 4">
            <Label value="HIGH" position="right" fontSize={10} fill={RISK_COLORS.HIGH} />
          </ReferenceLine>
          <ReferenceLine
            y={0.8}
            stroke={RISK_COLORS.CRITICAL}
            strokeDasharray="4 4"
          >
            <Label
              value="CRITICAL"
              position="right"
              fontSize={10}
              fill={RISK_COLORS.CRITICAL}
            />
          </ReferenceLine>
          {interventionPoints.map((point, index) => (
            <ReferenceDot
              key={`${point.timestamp}-${index}`}
              x={point.timestamp}
              y={point.churn_probability}
              r={6}
              fill="#3b82f6"
              stroke="white"
              strokeWidth={2}
              label={{ value: "⚡", position: "top", fontSize: 14 }}
            />
          ))}
          <Line
            type="monotone"
            dataKey="churn_probability"
            stroke="#6366f1"
            strokeWidth={2.5}
            dot={false}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
