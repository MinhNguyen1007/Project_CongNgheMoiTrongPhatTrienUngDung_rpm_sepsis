// Global state cho alert events từ WS. UI subscribe để hiện notification
// banner + sidebar badge count.
//
// WHY context thay vì store: scope nhỏ (1 list 50 alert gần nhất), không cần
// Redux/Zustand. useReducer đủ cho add/clear/markRead.
import { createContext, useCallback, useContext, useReducer } from "react";
import type { ReactNode } from "react";
import type { WSPredictionEvent } from "@/types/api";

interface AlertItem {
  id: string; // patient_id + hour, idempotent
  patient_id: string;
  hour: number;
  sepsis_risk: number;
  predicted_at: string;
  read: boolean;
}

interface State {
  alerts: AlertItem[]; // mới nhất ở đầu
}

type Action =
  | { type: "PUSH"; event: WSPredictionEvent }
  | { type: "MARK_ALL_READ" }
  | { type: "CLEAR" };

const MAX_ALERTS = 50;

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "PUSH": {
      // Chỉ giữ alert thực sự (event.alert=true). Event thường skip.
      if (!action.event.alert) return state;
      const id = `${action.event.patient_id}-${action.event.hour}`;
      // Dedupe — cùng (patient, hour) ko push 2 lần.
      if (state.alerts.some((a) => a.id === id)) return state;
      const next: AlertItem = {
        id,
        patient_id: action.event.patient_id,
        hour: action.event.hour,
        sepsis_risk: action.event.sepsis_risk,
        predicted_at: action.event.predicted_at,
        read: false,
      };
      return { alerts: [next, ...state.alerts].slice(0, MAX_ALERTS) };
    }
    case "MARK_ALL_READ":
      return { alerts: state.alerts.map((a) => ({ ...a, read: true })) };
    case "CLEAR":
      return { alerts: [] };
  }
}

interface AlertsContextValue {
  alerts: AlertItem[];
  unreadCount: number;
  push: (event: WSPredictionEvent) => void;
  markAllRead: () => void;
  clear: () => void;
}

const AlertsContext = createContext<AlertsContextValue | undefined>(undefined);

export function AlertsProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, { alerts: [] });

  const push = useCallback((event: WSPredictionEvent) => dispatch({ type: "PUSH", event }), []);
  const markAllRead = useCallback(() => dispatch({ type: "MARK_ALL_READ" }), []);
  const clear = useCallback(() => dispatch({ type: "CLEAR" }), []);

  const unreadCount = state.alerts.filter((a) => !a.read).length;

  return (
    <AlertsContext.Provider value={{ alerts: state.alerts, unreadCount, push, markAllRead, clear }}>
      {children}
    </AlertsContext.Provider>
  );
}

export function useAlertsContext() {
  const ctx = useContext(AlertsContext);
  if (!ctx) throw new Error("useAlertsContext phải dùng bên trong <AlertsProvider>");
  return ctx;
}

export type { AlertItem };
