"use client";

import { useEffect, useRef, useState } from "react";

import type { SSEChurnEvent } from "@/types/churn";

export function useChurnEventStream(apiBase: string) {
  const [events, setEvents] = useState<SSEChurnEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const es = new EventSource(`${apiBase}/api/v1/stream/churn-events`);
    esRef.current = es;

    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    es.onmessage = (e: MessageEvent) => {
      try {
        const event: SSEChurnEvent = JSON.parse(e.data);
        if (!event.event_type || event.event_type === ("HEARTBEAT" as never)) {
          return;
        }
        setEvents((prev) => [event, ...prev].slice(0, 50));
      } catch {
        // ignore malformed payloads (e.g. keepalive comments parsed incorrectly)
      }
    };

    return () => {
      es.close();
      setConnected(false);
    };
  }, [apiBase]);

  return { events, connected };
}
