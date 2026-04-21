import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useAlertStream } from "@/hooks/useAlertStream";
import { useAuthStore } from "@/stores/authStore";
import { useState } from "react";

export function AlertsFeed() {
  const queryClient = useQueryClient();
  const { events: wsEvents } = useAlertStream();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const role = useAuthStore((s) => s.role);
  const canAcknowledge = role === "admin" || role === "doctor";
  const [tab, setTab] = useState<"live" | "history">("live");

  // Persisted alerts from PostgreSQL
  const { data: dbAlerts, isLoading } = useQuery({
    queryKey: ["alerts"],
    queryFn: () => api.alerts({ limit: 100 }),
    refetchInterval: 10_000,
    enabled: isAuthenticated,
  });

  const ackMutation = useMutation({
    mutationFn: (id: number) => api.acknowledgeAlert(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });

  const tabClass = (active: boolean) =>
    `px-4 py-2 text-sm font-medium rounded-t-lg transition ${
      active
        ? "bg-white text-slate-900 border border-b-0 border-slate-200"
        : "text-slate-500 hover:text-slate-700 hover:bg-slate-50"
    }`;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-800">Cảnh báo</h2>
        <div className="flex gap-1">
          <button
            className={tabClass(tab === "live")}
            onClick={() => setTab("live")}
          >
            Live ({wsEvents.length})
          </button>
          <button
            className={tabClass(tab === "history")}
            onClick={() => setTab("history")}
          >
            Lịch sử {dbAlerts ? `(${dbAlerts.length})` : ""}
          </button>
        </div>
      </div>

      {tab === "live" ? (
        /* ── Live WS events ── */
        <div className="space-y-2">
          {wsEvents.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center">
              <p className="text-slate-500">Chưa có cảnh báo trực tiếp.</p>
              <p className="mt-1 text-xs text-slate-400">
                Alert sẽ xuất hiện khi model phát hiện nguy cơ sepsis.
              </p>
            </div>
          ) : (
            wsEvents.map((e, i) => (
              <div
                key={`${e.patient_id}-${e.timestamp}-${i}`}
                className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-4 py-3 shadow-sm"
              >
                <div className="flex items-center gap-3">
                  <span className="inline-block h-2.5 w-2.5 animate-pulse rounded-full bg-red-500" />
                  <div>
                    <span className="font-semibold text-red-800">
                      {e.patient_id}
                    </span>
                    <span className="ml-2 text-sm text-red-600">
                      Proba {(e.proba * 100).toFixed(1)}% · ICULOS{" "}
                      {e.iculos_hours}h
                    </span>
                  </div>
                </div>
                <span className="text-xs text-red-400">
                  {new Date(e.timestamp).toLocaleString()}
                </span>
              </div>
            ))
          )}
        </div>
      ) : (
        /* ── Persisted alerts from DB ── */
        <div className="space-y-2">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-200 border-t-sky-600" />
              <span className="ml-2 text-sm text-slate-500">
                Đang tải lịch sử...
              </span>
            </div>
          ) : !dbAlerts || dbAlerts.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center">
              <p className="text-slate-500">Chưa có cảnh báo nào được lưu.</p>
            </div>
          ) : (
            dbAlerts.map((a) => (
              <div
                key={a.id}
                className={`flex items-center justify-between rounded-lg border px-4 py-3 shadow-sm transition ${
                  a.acknowledged
                    ? "border-slate-200 bg-white"
                    : "border-amber-200 bg-amber-50"
                }`}
              >
                <div className="flex items-center gap-3">
                  {a.acknowledged ? (
                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-green-100">
                      <svg
                        className="h-3 w-3 text-green-600"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={3}
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M5 13l4 4L19 7"
                        />
                      </svg>
                    </span>
                  ) : (
                    <span className="inline-block h-2.5 w-2.5 rounded-full bg-amber-500" />
                  )}
                  <div>
                    <span className="font-semibold text-slate-800">
                      {a.patient_id}
                    </span>
                    <span className="ml-2 text-sm text-slate-600">
                      Proba {(a.proba * 100).toFixed(1)}% · streak{" "}
                      {a.consecutive_above} · ICULOS {a.iculos_hours}h
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-400">
                    {new Date(a.timestamp).toLocaleString()}
                  </span>
                  {a.acknowledged ? (
                    <span className="text-xs text-green-600">
                      ✓ {a.acknowledged_by}
                    </span>
                  ) : canAcknowledge ? (
                    <button
                      onClick={() => ackMutation.mutate(a.id)}
                      disabled={ackMutation.isPending}
                      className="rounded-md bg-sky-600 px-3 py-1 text-xs font-medium text-white shadow-sm transition hover:bg-sky-500 disabled:opacity-50"
                    >
                      {ackMutation.isPending ? "..." : "Xác nhận"}
                    </button>
                  ) : (
                    <span className="text-xs italic text-slate-400">
                      Chỉ đọc
                    </span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
