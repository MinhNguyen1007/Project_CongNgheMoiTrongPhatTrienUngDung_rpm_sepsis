import { Link } from "react-router-dom";

import { Loading } from "@/components/common/Loading";
import { RiskBadge } from "@/components/common/RiskBadge";
import { useAlerts } from "@/hooks/useAlerts";
import { useAlertsContext } from "@/context/AlertsContext";
import { formatRelativeTime } from "@/utils/formatters";

export function AlertPanel() {
  // 2 source alert:
  //   - Server (REST): /predictions/alerts — truth, dùng cho danh sách chính.
  //   - WS context: cho "vừa mới đến" indicator (chấm đỏ unread).
  const { data: serverAlerts, isLoading } = useAlerts({ hours_window: 24 });
  const { alerts: liveAlerts, markAllRead, clear } = useAlertsContext();

  // Tập patient_id có WS alert chưa đọc → hiển thị dot bên cạnh.
  const unreadIds = new Set(liveAlerts.filter((a) => !a.read).map((a) => a.patient_id));

  return (
    <section className="bg-white rounded-lg border border-slate-200 overflow-hidden">
      <header className="flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-red-50">
        <div className="flex items-center gap-2">
          <span className="text-red-600">🚨</span>
          <h3 className="font-semibold text-slate-800">High-Risk Alerts</h3>
          {(serverAlerts?.length ?? 0) > 0 && (
            <span className="bg-red-600 text-white text-xs font-bold rounded-full px-2 py-0.5">
              {serverAlerts!.length}
            </span>
          )}
        </div>
        <div className="flex gap-2 text-xs">
          <button
            type="button"
            onClick={markAllRead}
            className="text-slate-600 hover:text-slate-900"
          >
            Mark read
          </button>
          <button type="button" onClick={clear} className="text-slate-600 hover:text-slate-900">
            Clear live
          </button>
        </div>
      </header>

      <div className="max-h-96 overflow-auto divide-y divide-slate-100">
        {isLoading ? (
          <Loading message="Loading alerts..." />
        ) : !serverAlerts || serverAlerts.length === 0 ? (
          <div className="px-4 py-6 text-center text-slate-500 text-sm">
            No active alerts in last 24h.
          </div>
        ) : (
          serverAlerts.map((a) => (
            <Link
              key={`${a.patient_id}-${a.hour}`}
              to={`/patients/${a.patient_id}`}
              className="flex items-center justify-between px-4 py-3 hover:bg-slate-50 transition-colors"
            >
              <div>
                <div className="flex items-center gap-2">
                  {unreadIds.has(a.patient_id) && (
                    <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
                  )}
                  <span className="font-mono text-blue-600">{a.patient_id}</span>
                  <span className="text-slate-400 text-xs">hour {a.hour}</span>
                </div>
                <div className="text-xs text-slate-500 mt-0.5">
                  {formatRelativeTime(a.predicted_at)}
                </div>
              </div>
              <RiskBadge risk={a.sepsis_risk} size="sm" showPercent />
            </Link>
          ))
        )}
      </div>
    </section>
  );
}

