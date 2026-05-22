import { useState } from "react";
import { Link } from "react-router-dom";

import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";
import { RiskBadge } from "@/components/common/RiskBadge";
import { usePatients } from "@/hooks/usePatients";
import { formatAge, formatGender, formatRelativeTime, formatRiskPercent } from "@/utils/formatters";

const PAGE_SIZE = 15;

export function PatientList() {
  const { data, isLoading, error } = usePatients({ hours_window: 24, limit: 100 });
  const [page, setPage] = useState(0);

  if (isLoading) return <Loading message="Loading patients..." />;
  if (error) {
    return (
      <EmptyState
        title="Cannot load patients"
        description="Backend không phản hồi. Check `/api/patients` ở port 8000."
      />
    );
  }
  if (!data || data.length === 0) {
    return (
      <EmptyState
        title="No active patients"
        description="Chạy producer để stream vital signs vào hệ thống."
      />
    );
  }

  const totalPages = Math.ceil(data.length / PAGE_SIZE);
  const paged = data.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
      <div className="overflow-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600 text-left">
            <tr>
              <th className="px-4 py-2.5 font-medium">Patient ID</th>
              <th className="px-4 py-2.5 font-medium hidden sm:table-cell">Age</th>
              <th className="px-4 py-2.5 font-medium hidden sm:table-cell">Gender</th>
              <th className="px-4 py-2.5 font-medium">Risk</th>
              <th className="px-4 py-2.5 font-medium">Risk %</th>
              <th className="px-4 py-2.5 font-medium hidden md:table-cell">Last Update</th>
            </tr>
          </thead>
          <tbody className="tabular divide-y divide-slate-100">
            {paged.map((p) => (
              <tr key={p.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-4 py-2.5">
                  <Link to={`/patients/${p.id}`} className="text-blue-600 font-mono hover:underline">
                    {p.id}
                  </Link>
                </td>
                <td className="px-4 py-2.5 text-slate-700 hidden sm:table-cell">{formatAge(p.age)}</td>
                <td className="px-4 py-2.5 text-slate-700 hidden sm:table-cell">{formatGender(p.gender)}</td>
                <td className="px-4 py-2.5">
                  <RiskBadge risk={p.current_risk} size="sm" />
                </td>
                <td className="px-4 py-2.5 font-mono text-slate-700">
                  {formatRiskPercent(p.current_risk)}
                </td>
                <td className="px-4 py-2.5 text-slate-500 text-xs hidden md:table-cell">
                  {formatRelativeTime(p.last_updated)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-2.5 border-t border-slate-200 bg-slate-50 text-sm">
          <span className="text-slate-500">
            {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, data.length)} of {data.length}
          </span>
          <div className="flex gap-1">
            <button
              type="button"
              onClick={() => setPage((p) => p - 1)}
              disabled={page === 0}
              className="px-2.5 py-1 rounded border border-slate-300 text-slate-600 hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Prev
            </button>
            <button
              type="button"
              onClick={() => setPage((p) => p + 1)}
              disabled={page >= totalPages - 1}
              className="px-2.5 py-1 rounded border border-slate-300 text-slate-600 hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
