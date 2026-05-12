// Custom WebSocket hook với auto-reconnect exponential backoff + heartbeat.
//
// WHY callback trong useRef: nếu callback là dependency của useEffect, mỗi
// parent re-render sẽ close + reopen socket → mất event. Ref tách callback
// khỏi connection lifecycle.
import { useEffect, useRef, useState } from "react";

type Status = "connecting" | "open" | "closed";

interface Options<T> {
  url: string;
  onMessage: (event: T) => void;
  heartbeatMs?: number;
  maxBackoffMs?: number;
}

export function useWebSocket<T>({
  url,
  onMessage,
  heartbeatMs = 25_000,
  maxBackoffMs = 30_000,
}: Options<T>) {
  const [status, setStatus] = useState<Status>("connecting");
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectAttempts = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
    let closed = false;

    function connect() {
      setStatus("connecting");
      socket = new WebSocket(url);

      socket.onopen = () => {
        setStatus("open");
        reconnectAttempts = 0;
        // Heartbeat — backend WS endpoint chỉ cần thấy bất kỳ message để
        // detect alive. Server không reply, chỉ giữ keepalive.
        heartbeatTimer = setInterval(() => {
          if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send("ping");
          }
        }, heartbeatMs);
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as T;
          onMessageRef.current(data);
        } catch (err) {
          // Silent fail — server có thể gửi ping/pong text trong tương lai.
          console.warn("WS: cannot parse message", err);
        }
      };

      socket.onerror = () => {
        // onclose sẽ trigger ngay sau onerror, schedule reconnect ở đó.
      };

      socket.onclose = () => {
        setStatus("closed");
        if (heartbeatTimer) {
          clearInterval(heartbeatTimer);
          heartbeatTimer = null;
        }
        if (closed) return;

        // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s max.
        const delay = Math.min(1000 * 2 ** reconnectAttempts, maxBackoffMs);
        reconnectAttempts += 1;
        reconnectTimer = setTimeout(connect, delay);
      };
    }

    connect();

    return () => {
      closed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (heartbeatTimer) clearInterval(heartbeatTimer);
      socket?.close();
    };
  }, [url, heartbeatMs, maxBackoffMs]);

  return { status };
}
