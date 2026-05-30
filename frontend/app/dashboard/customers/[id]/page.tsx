import { Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow, Text } from "@tremor/react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ChurnTimelineChart } from "@/components/ChurnTimelineChart";
import { RiskBadge } from "@/components/RiskBadge";
import {
  getCustomer,
  getCustomerChurnTimeline,
  getFeatureImportance,
} from "@/lib/api";
import { ApiError } from "@/lib/api";

export const dynamic = "force-dynamic";

interface Props {
  params: { id: string };
}

export default async function CustomerDetailPage({ params }: Props) {
  let customer;
  let timeline;

  try {
    [customer, timeline] = await Promise.all([
      getCustomer(params.id),
      getCustomerChurnTimeline(params.id),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }

  const featureImportance = await getFeatureImportance("latest");
  const contributions =
    customer.churn.top_contributing_features.length > 0
      ? customer.churn.top_contributing_features
      : featureImportance.features.slice(0, 5).map((feature) => ({
          feature: feature.feature,
          shap_value: feature.avg_shap_value,
          direction: feature.direction,
        }));

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link
            href="/dashboard/customers"
            className="text-sm text-indigo-600 hover:underline"
          >
            ← Customers
          </Link>
          <h1 className="mt-2 text-2xl font-bold text-gray-900">{customer.full_name}</h1>
          <p className="text-sm text-gray-500">
            {customer.phone_primary} · {customer.account_status} ·{" "}
            {customer.contract_type ?? "No contract"}
          </p>
        </div>
        <RiskBadge tier={customer.churn.risk_tier} className="text-sm" />
      </header>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card>
          <Text>Current Score</Text>
          <p className="text-tremor-metric font-semibold text-tremor-content-strong">
            {(timeline.current_score * 100).toFixed(1)}%
          </p>
        </Card>
        <Card>
          <Text>90d Net Change</Text>
          <p
            className={`text-tremor-metric font-semibold ${
              timeline.net_change < 0 ? "text-green-600" : "text-red-600"
            }`}
          >
            {timeline.net_change > 0 ? "+" : ""}
            {(timeline.net_change * 100).toFixed(1)}%
          </p>
        </Card>
        <Card>
          <Text>Interventions</Text>
          <p className="text-tremor-metric font-semibold text-tremor-content-strong">
            {timeline.interventions_count}
          </p>
        </Card>
      </div>

      <Card>
        <Text>Churn Probability Timeline</Text>
        <div className="mt-4">
          <ChurnTimelineChart
            data={timeline.data_points}
            savedByAI={timeline.saved_by_ai}
          />
        </div>
      </Card>

      <Card>
        <Text>Feature Contributions</Text>
        <Text className="text-tremor-content-subtle text-sm">
          Source: customer churn snapshot
          {featureImportance.source === "aggregated_churn_scores"
            ? " + portfolio SHAP aggregates"
            : " (portfolio aggregates when per-customer SHAP unavailable)"}
        </Text>
        {contributions.length === 0 ? (
          <p className="mt-4 text-sm text-gray-500">
            No SHAP contributions yet — scores will populate after model training.
          </p>
        ) : (
          <Table className="mt-4">
            <TableHead>
              <TableRow>
                <TableHeaderCell>Feature</TableHeaderCell>
                <TableHeaderCell>SHAP</TableHeaderCell>
                <TableHeaderCell>Direction</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {contributions.map((row) => (
                <TableRow key={row.feature}>
                  <TableCell>{row.feature}</TableCell>
                  <TableCell>{row.shap_value.toFixed(4)}</TableCell>
                  <TableCell>
                    <span
                      className={
                        row.direction === "INCREASES_RISK"
                          ? "text-red-600"
                          : "text-green-600"
                      }
                    >
                      {row.direction.replace(/_/g, " ")}
                    </span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      <Card>
        <Text>Open Tickets</Text>
        {customer.open_tickets.length === 0 ? (
          <p className="mt-3 text-sm text-gray-500">No open tickets.</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {customer.open_tickets.map((ticket) => (
              <li
                key={ticket.ticket_id}
                className="rounded-lg border border-gray-100 px-3 py-2 text-sm"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{ticket.subject}</span>
                  <span className="text-xs text-gray-500">{ticket.priority}</span>
                </div>
                <p className="text-xs text-gray-500">
                  {ticket.ticket_type} · {ticket.status}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
