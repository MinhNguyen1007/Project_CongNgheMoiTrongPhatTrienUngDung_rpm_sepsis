// Drift Reports page — list các drift report từ Evidently job (T6).
// Hiện T5 chưa có data, hiển thị EmptyState + giải thích.
import { EmptyState } from "@/components/common/EmptyState";
import { Loading } from "@/components/common/Loading";
import { useDriftReports } from "@/hooks/useModelInfo";
import { formatRelativeTime } from "@/utils/formatters";

export default function DriftReports() {
  const { data, isLoading } = useDriftReports(20);

  if (isLoading) return <Loading />;

  return (
    <div className="space-y-5 max-w-5xl mx-auto">
      <div>
        <h2 className="text-2xl font-bold">Drift Reports</h2>
        <p className="text-slate-600 text-sm mt-1">
          Daily Evidently checks — flag retrain khi feature drift &gt; threshold.
        </p>
      </div>

      {!data || data.length === 0 ? (
        <EmptyState
          title="No drift reports yet"
          description="Drift detection job (T6) chưa chạy. Sau khi enable APScheduler, daily 2AM sẽ tạo report."
        />
      ) : (
        <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
          <table className="w-full text-sm tabular">
            <thead className="bg-slate-50 text-slate-600 text-left">
              <tr>
                <th className="px-4 py-2.5 font-medium">ID</th>
                <th className="px-4 py-2.5 font-medium">Reference period</th>
                <th className="px-4 py-2.5 font-medium">Target period</th>
                <th className="px-4 py-2.5 font-medium">Drift share</th>
                <th className="px-4 py-2.5 font-medium">Triggered retrain</th>
                <th className="px-4 py-2.5 font-medium">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.map((r) => (
                <tr key={r.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2.5 font-mono">#{r.id}</td>
                  <td className="px-4 py-2.5 text-xs text-slate-600">
                    {fmtDate(r.ref_period_start)} → {fmtDate(r.ref_period_end)}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-slate-600">
                    {fmtDate(r.target_period_start)} → {fmtDate(r.target_period_end)}
                  </td>
                  <td className="px-4 py-2.5">
                    <span
                      className={`font-mono ${
                        r.drift_share >= 0.3 ? "text-red-600 font-bold" : "text-slate-700"
                      }`}
                    >
                      {(r.drift_share * 100).toFixed(1)}%
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    {r.triggered_retrain ? (
                      <span className="px-2 py-0.5 bg-red-100 text-red-700 rounded text-xs font-semibold">
                        YES
                      </span>
                    ) : (
                      <span className="text-slate-400">no</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-slate-500">
                    {formatRelativeTime(r.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString();
}
