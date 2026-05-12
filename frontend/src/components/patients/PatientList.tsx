import { Link } from "react-router-dom";

import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";
import { RiskBadge } from "@/components/common/RiskBadge";
import { usePatients } from "@/hooks/usePatients";
import { formatAge, formatGender, formatRelativeTime, formatRiskPercent } from "@/utils/formatters";

export function PatientList() {
  const { data, isLoading, error } = usePatients({ hours_window: 24, limit: 100 });

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

  return (
    <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-slate-600 text-left">
          <tr>
            <th className="px-4 py-2.5 font-medium">Patient ID</th>
            <th className="px-4 py-2.5 font-medium">Age</th>
            <th className="px-4 py-2.5 font-medium">Gender</th>
            <th className="px-4 py-2.5 font-medium">Risk</th>
            <th className="px-4 py-2.5 font-medium">Risk %</th>
            <th className="px-4 py-2.5 font-medium">Last Update</th>
          </tr>
        </thead>
        <tbody className="tabular divide-y divide-slate-100">
          {data.map((p) => (
            <tr key={p.id} className="hover:bg-slate-50 transition-colors">
              <td className="px-4 py-2.5">
                <Link to={`/patients/${p.id}`} className="text-blue-600 font-mono hover:underline">
                  {p.id}
                </Link>
              </td>
              <td className="px-4 py-2.5 text-slate-700">{formatAge(p.age)}</td>
              <td className="px-4 py-2.5 text-slate-700">{formatGender(p.gender)}</td>
              <td className="px-4 py-2.5">
                <RiskBadge risk={p.current_risk} size="sm" />
              </td>
              <td className="px-4 py-2.5 font-mono text-slate-700">
                {formatRiskPercent(p.current_risk)}
              </td>
              <td className="px-4 py-2.5 text-slate-500 text-xs">
                {formatRelativeTime(p.last_updated)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
