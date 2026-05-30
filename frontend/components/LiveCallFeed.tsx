"use client";

import { Card, Text } from "@tremor/react";
import { format, parseISO } from "date-fns";
import Link from "next/link";
import { useEffect, useState } from "react";

import { getApiBaseUrl } from "@/lib/api";
import { useChurnEventStream } from "@/lib/sse";
import type { SSEChurnEvent } from "@/types/churn";
import { RiskBadge } from "@/components/RiskBadge";

function EventCard({ event }: { event: SSEChurnEvent }) {
  return (
    <div className="rounded-lg border border-gray-100 bg-white p-3 text-sm shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold text-gray-800">{event.event_type.replace(/_/g, " ")}</span>
        <span className="text-xs text-gray-400">
          {event.timestamp ? format(parseISO(event.timestamp), "HH:mm:ss") : "—"}
        </span>
      </div>

      {event.customer_name && (
        <p className="mt-1 font-medium">
          {event.customer_id ? (
            <Link
              href={`/dashboard/customers/${event.customer_id}`}
              className="text-indigo-600 hover:underline"
            >
              {event.customer_name}
            </Link>
          ) : (
            event.customer_name
          )}
        </p>
      )}

      {event.churn_risk_tier && (
        <div className="mt-2">
          <RiskBadge tier={event.churn_risk_tier} />
          {event.churn_probability !== undefined && (
            <span className="ml-2 text-xs text-gray-500">
              {(event.churn_probability * 100).toFixed(0)}% churn risk
            </span>
          )}
        </div>
      )}

      {event.event_type === "INTERVENTION_COMPLETE" && (
        <p className="mt-2 text-xs text-green-700">
          Score {(event.score_before ?? 0) * 100}% → {(event.score_after ?? 0) * 100}%
          {event.saved_by_ai ? " · Saved by AI" : ""}
          {event.job_number ? ` · Job ${event.job_number}` : ""}
        </p>
      )}

      {event.event_type === "BATCH_SCORE_COMPLETE" && (
        <p className="mt-2 text-xs text-gray-600">
          Scored {event.accounts_scored ?? 0} accounts · +{event.new_critical ?? 0} critical ·
          −{event.resolved_critical ?? 0} resolved
        </p>
      )}
    </div>
  );
}

export function LiveCallFeed() {
  const apiBase = getApiBaseUrl();
  const { events, connected } = useChurnEventStream(apiBase);
  const [toast, setToast] = useState<SSEChurnEvent | null>(null);

  useEffect(() => {
    const latest = events[0];
    if (
      latest?.event_type === "CALL_ACTIVE" &&
      latest.churn_risk_tier === "CRITICAL"
    ) {
      setToast(latest);
      const timer = setTimeout(() => setToast(null), 8000);
      return () => clearTimeout(timer);
    }
  }, [events]);

  return (
    <Card className="relative flex h-full flex-col">
      <div className="flex items-center justify-between">
        <Text>Live Activity Feed</Text>
        <span
          className={`text-xs font-medium ${connected ? "text-green-600" : "text-red-500"}`}
        >
          {connected ? "● Connected" : "○ Disconnected"}
        </span>
      </div>

      {toast && (
        <div
          role="alert"
          className="absolute left-4 right-4 top-14 z-20 rounded-lg border border-red-300 bg-red-50 p-3 shadow-lg"
        >
          <p className="text-sm font-bold text-red-800">CRITICAL call in progress</p>
          <p className="text-xs text-red-700">
            {toast.customer_name} — {(toast.churn_probability ?? 0) * 100}% churn risk
          </p>
        </div>
      )}

      <div className="mt-4 max-h-96 flex-1 overflow-y-auto pr-1">
        {events.length === 0 ? (
          <p className="text-sm text-gray-500">
            Waiting for events from SSE stream… Start a HIGH/CRITICAL call to see
            activity.
          </p>
        ) : (
          <div className="space-y-3">
            {events.map((event, index) => (
              <EventCard key={`${event.timestamp}-${index}`} event={event} />
            ))}
          </div>
        )}
      </div>

      <p className="mt-3 text-xs text-gray-400">
        Accounts saved today:{" "}
        {events.filter((e) => e.event_type === "INTERVENTION_COMPLETE" && e.saved_by_ai).length}
      </p>
    </Card>
  );
}
