// Wrapper context: khởi tạo WS connection 1 lần ở app level, push event
// về AlertsContext + invalidate React Query cache để list patient refresh.
import { createContext, useContext } from "react";
import type { ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useWebSocket } from "@/hooks/useWebSocket";
import { useAlertsContext } from "@/context/AlertsContext";
import type { PatientSummary, WSPredictionEvent } from "@/types/api";

type Status = "connecting" | "open" | "closed";

const WebSocketContext = createContext<{ status: Status }>({ status: "connecting" });

// WHY resolveWsUrl: VITE_WS_URL bake tại build time. Image build trong CI dùng
// ws://localhost/... → trên EC2 IP khác, browser load index → JS connect localhost FAIL.
// Giải pháp: nếu env là path-only ("/ws/...") thì resolve runtime theo window.location.
// → 1 image dùng được cho localhost + bất kỳ EC2 IP/domain.
function resolveWsUrl(envUrl: string): string {
  if (envUrl.startsWith("ws://") || envUrl.startsWith("wss://")) return envUrl;
  const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
  const path = envUrl.startsWith("/") ? envUrl : `/${envUrl}`;
  return `${scheme}//${window.location.host}${path}`;
}

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const { push } = useAlertsContext();

  const { status } = useWebSocket<WSPredictionEvent>({
    url: resolveWsUrl(import.meta.env.VITE_WS_URL),
    onMessage: (event) => {
      // WHY setQueriesData thay vì invalidateQueries cho patients: update cache
      // trực tiếp = instant render, không cần HTTP round-trip (~300-500ms) mỗi event.
      // Nếu patient chưa có trong list (mới) → fallback invalidate để fetch về.
      let patientFound = false;
      queryClient.setQueriesData<PatientSummary[]>(
        { queryKey: ["patients"] },
        (old) => {
          if (!old) return old;
          const idx = old.findIndex((p) => p.id === event.patient_id);
          if (idx === -1) return old;
          patientFound = true;
          const updated = [...old];
          updated[idx] = {
            ...updated[idx],
            current_risk: event.sepsis_risk,
            last_updated: event.predicted_at,
          };
          return updated;
        },
      );
      if (!patientFound) {
        queryClient.invalidateQueries({ queryKey: ["patients"] });
      }

      queryClient.invalidateQueries({ queryKey: ["alerts"] });
      queryClient.invalidateQueries({ queryKey: ["patient-predictions", event.patient_id] });
      queryClient.invalidateQueries({ queryKey: ["patient-vitals", event.patient_id] });

      push(event);
    },
  });

  return <WebSocketContext.Provider value={{ status }}>{children}</WebSocketContext.Provider>;
}

export function useWebSocketStatus() {
  return useContext(WebSocketContext).status;
}
