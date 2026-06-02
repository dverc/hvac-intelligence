"use client";

import {
  Card,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
  Text,
} from "@tremor/react";
import { format, parseISO } from "date-fns";
import { Fragment, useEffect, useState } from "react";

import { ApiError, getCustomerTranscripts } from "@/lib/api";
import type { TranscriptMessage, TranscriptSummary } from "@/types/transcript";

interface CallHistorySectionProps {
  customerId: string;
}

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) {
    return "—";
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes === 0) {
    return `${remainingSeconds}s`;
  }
  return `${minutes}m ${remainingSeconds}s`;
}

function formatCost(cost: number | null): string {
  if (cost === null || cost === undefined) {
    return "—";
  }
  return `$${cost.toFixed(2)}`;
}

function formatDateTime(iso: string | null): string {
  if (!iso) {
    return "—";
  }
  return format(parseISO(iso), "MMM d, yyyy · h:mm a");
}

function isAssistantMessage(message: TranscriptMessage): boolean {
  const role = (message.role ?? message.speaker ?? "").toLowerCase();
  return role === "assistant" || role === "agent";
}

function messageText(message: TranscriptMessage): string {
  return message.message ?? message.text ?? message.content ?? "";
}

function normalizeMessages(
  transcript: TranscriptSummary,
): TranscriptMessage[] {
  if (Array.isArray(transcript.transcript_json)) {
    return transcript.transcript_json;
  }
  if (transcript.transcript_raw) {
    return [{ speaker: "customer", text: transcript.transcript_raw }];
  }
  return [];
}

function TranscriptPanel({ transcript }: { transcript: TranscriptSummary }) {
  const messages = normalizeMessages(transcript);
  const [showToolLog, setShowToolLog] = useState(false);

  return (
    <div className="mt-4 space-y-4 rounded-lg border border-gray-100 bg-gray-50 p-4">
      {transcript.call_summary && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
            Call Summary
          </p>
          <p className="mt-1 text-sm text-gray-800">{transcript.call_summary}</p>
        </div>
      )}

      {messages.length > 0 ? (
        <div className="space-y-3">
          {messages.map((message, index) => {
            const assistant = isAssistantMessage(message);
            return (
              <div
                key={`${transcript.call_id}-${index}`}
                className={`flex ${assistant ? "justify-start" : "justify-end"}`}
              >
                <div
                  className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                    assistant
                      ? "bg-white text-gray-800 shadow-sm"
                      : "bg-indigo-600 text-white"
                  }`}
                >
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide opacity-70">
                    {assistant ? "Assistant" : "Customer"}
                  </p>
                  <p>{messageText(message)}</p>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-sm text-gray-500">No transcript messages available.</p>
      )}

      {transcript.recording_url && (
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
            Recording
          </p>
          <audio controls className="w-full" src={transcript.recording_url}>
            Your browser does not support the audio element.
          </audio>
        </div>
      )}

      {transcript.tool_calls_log && transcript.tool_calls_log.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setShowToolLog((open) => !open)}
            className="text-sm font-medium text-indigo-600 hover:underline"
          >
            {showToolLog ? "Hide" : "Show"} tool calls log
          </button>
          {showToolLog && (
            <pre className="mt-2 max-h-48 overflow-auto rounded-lg bg-gray-900 p-3 text-xs text-gray-100">
              {JSON.stringify(transcript.tool_calls_log, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

export function CallHistorySection({ customerId }: CallHistorySectionProps) {
  const [transcripts, setTranscripts] = useState<TranscriptSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedCallId, setExpandedCallId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadTranscripts() {
      setLoading(true);
      setError(null);
      try {
        const response = await getCustomerTranscripts(customerId);
        if (!cancelled) {
          setTranscripts(response.transcripts);
        }
      } catch (err) {
        if (!cancelled) {
          const message =
            err instanceof ApiError
              ? err.message
              : "Failed to load call history.";
          setError(message);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadTranscripts();

    return () => {
      cancelled = true;
    };
  }, [customerId]);

  return (
    <Card>
      <Text>Call History</Text>

      {loading && (
        <p className="mt-3 text-sm text-gray-500">Loading call history…</p>
      )}

      {error && !loading && (
        <p className="mt-3 text-sm text-red-600">{error}</p>
      )}

      {!loading && !error && transcripts.length === 0 && (
        <p className="mt-3 text-sm text-gray-500">
          No calls recorded yet. Calls will appear here after the first inbound
          call from this customer.
        </p>
      )}

      {!loading && !error && transcripts.length > 0 && (
        <Table className="mt-4">
          <TableHead>
            <TableRow>
              <TableHeaderCell>Date &amp; Time</TableHeaderCell>
              <TableHeaderCell>Duration</TableHeaderCell>
              <TableHeaderCell>Outcome</TableHeaderCell>
              <TableHeaderCell>Cost</TableHeaderCell>
              <TableHeaderCell>End Reason</TableHeaderCell>
              <TableHeaderCell>Actions</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {transcripts.map((transcript) => {
              const isExpanded = expandedCallId === transcript.call_id;
              return (
                <Fragment key={transcript.call_id}>
                  <TableRow>
                    <TableCell>
                      {formatDateTime(transcript.call_start_utc)}
                    </TableCell>
                    <TableCell>
                      {formatDuration(transcript.duration_seconds)}
                    </TableCell>
                    <TableCell>
                      {transcript.call_outcome?.replace(/_/g, " ") ?? "—"}
                    </TableCell>
                    <TableCell>{formatCost(transcript.call_cost_usd)}</TableCell>
                    <TableCell>{transcript.vapi_end_reason ?? "—"}</TableCell>
                    <TableCell>
                      <button
                        type="button"
                        onClick={() =>
                          setExpandedCallId(
                            isExpanded ? null : transcript.call_id,
                          )
                        }
                        className="rounded-md bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-100"
                      >
                        {isExpanded ? "Hide Transcript" : "View Transcript"}
                      </button>
                    </TableCell>
                  </TableRow>
                  {isExpanded && (
                    <TableRow>
                      <TableCell colSpan={6}>
                        <TranscriptPanel transcript={transcript} />
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              );
            })}
          </TableBody>
        </Table>
      )}
    </Card>
  );
}
