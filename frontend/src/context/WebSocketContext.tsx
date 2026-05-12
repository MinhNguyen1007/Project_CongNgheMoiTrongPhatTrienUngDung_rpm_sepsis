// Wrapper context: khởi tạo WS connection 1 lần ở app level, push event
// về AlertsContext + invalidate React Query cache để list patient refresh.
import { createContext, useContext } from "react";
import type { ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useWebSocket } from "@/hooks/useWebSocket";
import { useAlertsContext } from "@/context/AlertsContext";
import type { WSPredictionEvent } from "@/types/api";

type Status = "connecting" | "open" | "closed";

const WebSocketContext = createContext<{ status: Status }>({ status: "connecting" });

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const { push } = useAlertsContext();

  const { status } = useWebSocket<WSPredictionEvent>({
    url: import.meta.env.VITE_WS_URL,
    onMessage: (event) => {
      // WHY invalidate: list patient + alerts dùng React Query cache. Khi có
      // prediction mới, invalidate để hook refetch. Throttle ko cần vì backend
      // gửi ~1 msg/giây, refetch debounced bởi staleTime 10s.
      queryClient.invalidateQueries({ queryKey: ["patients"] });
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
      queryClient.invalidateQueries({ queryKey: ["patient-predictions", event.patient_id] });
      queryClient.invalidateQueries({ queryKey: ["patient-vitals", event.patient_id] });

      // Push alert vào global state nếu event.alert=true.
      push(event);
    },
  });

  return <WebSocketContext.Provider value={{ status }}>{children}</WebSocketContext.Provider>;
}

export function useWebSocketStatus() {
  return useContext(WebSocketContext).status;
}
