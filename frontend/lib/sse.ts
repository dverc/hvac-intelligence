"use client";

import { useEffect, useRef, useState } from "react";

import { fetchChurnEventsSseToken, getChurnEventsStreamUrl } from "@/lib/api";
import type { SSEChurnEvent } from "@/types/churn";

const RECONNECT_DELAY_MS = 3000;
const MAX_RECONNECT_ATTEMPTS = 5;

export function useChurnEventStream() {
  const [events, setEvents] = useState<SSEChurnEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;

    function clearReconnectTimer() {
      if (reconnectTimerRef.current !== null) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    }

    function closeEventSource() {
      if (esRef.current !== null) {
        esRef.current.close();
        esRef.current = null;
      }
    }

    function scheduleReconnect(connect: () => Promise<void>) {
      if (cancelled) {
        return;
      }
      if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
        setConnected(false);
        setReconnecting(false);
        return;
      }
      reconnectAttemptsRef.current += 1;
      setReconnecting(true);
      setConnected(false);
      clearReconnectTimer();
      reconnectTimerRef.current = setTimeout(() => {
        void connect();
      }, RECONNECT_DELAY_MS);
    }

    async function connect() {
      clearReconnectTimer();
      closeEventSource();

      const sseToken = await fetchChurnEventsSseToken();
      if (cancelled) {
        return;
      }
      if (!sseToken) {
        console.error("[SSE] No stream token available; scheduling reconnect");
        scheduleReconnect(connect);
        return;
      }

      const es = new EventSource(getChurnEventsStreamUrl(sseToken));
      esRef.current = es;

      es.onopen = () => {
        reconnectAttemptsRef.current = 0;
        setConnected(true);
        setReconnecting(false);
      };

      es.onerror = () => {
        closeEventSource();
        scheduleReconnect(connect);
      };

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
    }

    void connect();

    return () => {
      cancelled = true;
      clearReconnectTimer();
      closeEventSource();
      setConnected(false);
      setReconnecting(false);
    };
  }, []);

  return { events, connected, reconnecting };
}
