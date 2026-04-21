import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { usePatientsStore } from "@/stores/patientsStore";
import { Badge } from "@/components/ui/Badge";
import type { PatientSummary } from "@/types/api";

function probaTone(p: number): "ok" | "warn" | "critical" {
  if (p >= 0.5) return "critical";
  if (p >= 0.1) return "warn";
  return "ok";
}

export function PatientList() {
  // Primary source: server polling every 5s
  const { data: serverPatients, isLoading } = useQuery({
    queryKey: ["patients"],
    queryFn: api.patients,
    refetchInterval: 5_000,
  });

  // Secondary: WS-driven client-side state (for optimistic live updates)
  const wsPatients = usePatientsStore((s) => s.patients);

  // Merge: server is source of truth; overlay WS updates for patients
  // not yet in the server response (or with fresher data)
  const merged = new Map<string, PatientSummary>();

  // Start with server data
  if (serverPatients) {
    for (const p of serverPatients) {
      merged.set(p.patient_id, p);
    }
  }

  // Overlay WS-only patients (those not in server yet, or with newer proba)
  for (const [pid, wsP] of Object.entries(wsPatients)) {
    const existing = merged.get(pid);
    if (!existing) {
      merged.set(pid, wsP);
    } else if (wsP.last_update > existing.last_update) {
      merged.set(pid, { ...existing, ...wsP });
    }
  }

  const sorted = Array.from(merged.values()).sort(
    (a, b) => b.latest_proba - a.latest_proba,
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-sky-600" />
        <span className="ml-3 text-slate-500">Loading patients...</span>
      </div>
    );
  }

  if (sorted.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-slate-300 bg-white p-12 text-center">
        <p className="text-slate-600">Chưa có dữ liệu bệnh nhân nào.</p>
        <p className="mt-1 text-sm text-slate-400">
          Khi consumer đẩy dữ liệu vào <code>/predict</code> và pipeline chạy,
          bệnh nhân sẽ xuất hiện ở đây.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-800">
          Danh sách bệnh nhân ({sorted.length})
        </h2>
        <span className="text-xs text-slate-400">
          Auto-refresh mỗi 5s · WS overlay trực tiếp
        </span>
      </div>
      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <table className="min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                Patient
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                Probability
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                Status
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                ICULOS (h)
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                Cập nhật
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {sorted.map((p) => (
              <tr
                key={p.patient_id}
                className="transition-colors hover:bg-slate-50"
              >
                <td className="px-4 py-3 font-medium text-slate-900">
                  <Link
                    to={`/patients/${p.patient_id}`}
                    className="text-sky-700 hover:underline"
                  >
                    {p.patient_id}
                  </Link>
                </td>
                <td className="px-4 py-3">
                  <Badge tone={probaTone(p.latest_proba)}>
                    {(p.latest_proba * 100).toFixed(1)}%
                  </Badge>
                </td>
                <td className="px-4 py-3">
                  {p.latest_alarm ? (
                    <span className="inline-flex items-center gap-1 text-xs font-medium text-red-600">
                      <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-red-500" />
                      ALARM
                    </span>
                  ) : (
                    <span className="text-xs text-slate-400">normal</span>
                  )}
                </td>
                <td className="px-4 py-3 text-slate-700">{p.iculos_hours}</td>
                <td className="px-4 py-3 text-sm text-slate-500">
                  {p.last_update
                    ? new Date(p.last_update).toLocaleString()
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
