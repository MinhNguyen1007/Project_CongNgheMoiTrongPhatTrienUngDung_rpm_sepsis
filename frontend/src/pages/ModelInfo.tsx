// Model Registry page — list version + production info + reload button.
//
// WHY có 2 source data: useModelCurrentInfo() là model đang load in-memory
// backend (truth-of-runtime), useModels() là history từ DB (truth-of-record).
import { useState } from "react";

import { apiClient } from "@/api/client";
import { EmptyState } from "@/components/common/EmptyState";
import { Loading } from "@/components/common/Loading";
import { useModelCurrentInfo, useModels } from "@/hooks/useModelInfo";
import { formatRelativeTime } from "@/utils/formatters";

export default function ModelInfo() {
  const { data: current, isLoading: cLoading } = useModelCurrentInfo();
  const { data: history, isLoading: hLoading, refetch } = useModels();
  const [reloading, setReloading] = useState(false);
  const [reloadMsg, setReloadMsg] = useState<string | null>(null);

  async function handleReload() {
    setReloading(true);
    setReloadMsg(null);
    try {
      const { data } = await apiClient.post<{ status: string; version: string }>(
        "/api/models/reload"
      );
      setReloadMsg(`Reloaded → version ${data.version}`);
      await refetch();
    } catch (err) {
      setReloadMsg(`Reload failed: ${(err as Error).message}`);
    } finally {
      setReloading(false);
    }
  }

  if (cLoading || hLoading) return <Loading />;

  return (
    <div className="space-y-5 max-w-5xl mx-auto">
      <div>
        <h2 className="text-2xl font-bold">Model Registry</h2>
        <p className="text-slate-600 text-sm mt-1">
          XGBoost sepsis-predictor — managed by MLflow.
        </p>
      </div>

      {/* Current in-memory model */}
      <section className="bg-white border border-slate-200 rounded-lg p-5">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="font-semibold text-slate-700 uppercase text-sm tracking-wide mb-3">
              Active production model
            </h3>
            {current ? (
              <div className="grid grid-cols-3 gap-4 tabular">
                <Stat label="Version" value={`v${current.version}`} />
                <Stat label="Threshold" value={current.threshold.toFixed(2)} />
                <Stat label="Features" value={current.n_features.toString()} />
              </div>
            ) : (
              <p className="text-slate-500">No model loaded.</p>
            )}
          </div>
          <button
            type="button"
            onClick={handleReload}
            disabled={reloading}
            className="px-3 py-1.5 rounded bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {reloading ? "Reloading..." : "Reload from MLflow"}
          </button>
        </div>
        {reloadMsg && <p className="mt-3 text-sm text-slate-600">{reloadMsg}</p>}
      </section>

      {/* Version history (DB-backed) */}
      <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <header className="px-4 py-3 border-b border-slate-200">
          <h3 className="font-semibold text-slate-700 uppercase text-sm tracking-wide">
            Version history
          </h3>
        </header>
        {!history || history.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title="No version recorded in DB yet"
              description="DB chỉ ghi version sau khi retrain job chạy (T6). Hiện tại chỉ có version đang load in-memory."
            />
          </div>
        ) : (
          <table className="w-full text-sm tabular">
            <thead className="bg-slate-50 text-slate-600 text-left">
              <tr>
                <th className="px-4 py-2.5 font-medium">Version</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium">AUROC</th>
                <th className="px-4 py-2.5 font-medium">AUPRC</th>
                <th className="px-4 py-2.5 font-medium">Utility</th>
                <th className="px-4 py-2.5 font-medium">Threshold</th>
                <th className="px-4 py-2.5 font-medium">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {history.map((m) => (
                <tr key={m.version} className="hover:bg-slate-50">
                  <td className="px-4 py-2.5 font-mono">v{m.version}</td>
                  <td className="px-4 py-2.5">
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-semibold ${
                        m.status === "production"
                          ? "bg-green-100 text-green-700"
                          : "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {m.status}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">{m.auroc?.toFixed(3) ?? "—"}</td>
                  <td className="px-4 py-2.5">{m.auprc?.toFixed(3) ?? "—"}</td>
                  <td className="px-4 py-2.5">{m.utility?.toFixed(3) ?? "—"}</td>
                  <td className="px-4 py-2.5">{m.threshold?.toFixed(2) ?? "—"}</td>
                  <td className="px-4 py-2.5 text-slate-500 text-xs">
                    {formatRelativeTime(m.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-slate-500 uppercase">{label}</div>
      <div className="text-2xl font-bold text-slate-800 mt-0.5">{value}</div>
    </div>
  );
}
