import { useEffect, useRef, useState } from "react";
import type { AlertEvent } from "@/types/api";

const WS_URL = import.meta.env.VITE_WS_URL ?? "/ws/alerts";
const MAX_BUFFER = 200;

export type AlertStreamStatus = "connecting" | "open" | "closed";

export interface UseAlertStreamResult {
  events: AlertEvent[];
  status: AlertStreamStatus;
  lastEvent: AlertEvent | null;
}

export function useAlertStream(): UseAlertStreamResult {
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [status, setStatus] = useState<AlertStreamStatus>("connecting");
  const [lastEvent, setLastEvent] = useState<AlertEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      setStatus("connecting");
      const url = WS_URL.startsWith("ws")
        ? WS_URL
        : `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}${WS_URL}`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => setStatus("open");
      ws.onclose = () => {
        setStatus("closed");
        if (!cancelled) {
          reconnectTimer.current = window.setTimeout(connect, 2000);
        }
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data as string) as AlertEvent;
          if (data.event !== "alert") return;
          setLastEvent(data);
          setEvents((prev) => [data, ...prev].slice(0, MAX_BUFFER));
        } catch {
          // ignore malformed frames
        }
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer.current) window.clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, []);

  return { events, status, lastEvent };
}
