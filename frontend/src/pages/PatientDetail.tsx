// Patient detail page: vital chart + risk timeline + info card + latest vitals table.
import { Link, useParams } from "react-router-dom";

import { RiskTimeline } from "@/components/charts/RiskTimeline";
import { VitalsChart } from "@/components/charts/VitalsChart";
import { EmptyState } from "@/components/common/EmptyState";
import { Loading } from "@/components/common/Loading";
import { RiskBadge } from "@/components/common/RiskBadge";
import { usePatientPredictions } from "@/hooks/useAlerts";
import { useModelCurrentInfo } from "@/hooks/useModelInfo";
import { usePatientVitals } from "@/hooks/usePatients";
import { formatRelativeTime, formatVital } from "@/utils/formatters";

export default function PatientDetail() {
  const { patientId } = useParams<{ patientId: string }>();
  const { data: vitals, isLoading: vLoading, error: vError } = usePatientVitals(patientId, 100);
  const { data: predictions, isLoading: pLoading } = usePatientPredictions(patientId, 200);
  const { data: modelInfo } = useModelCurrentInfo();

  if (vLoading || pLoading) return <Loading />;
  if (vError || !vitals || vitals.length === 0) {
    return (
      <EmptyState
        title={`No data for patient ${patientId}`}
        description="Patient chưa có vital trong hệ thống — chạy producer trước."
      />
    );
  }

  const latest = vitals[vitals.length - 1];
  const latestPred = predictions?.[predictions.length - 1];
  const threshold = modelInfo?.threshold ?? 0.7;

  return (
    <div className="space-y-5 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <Link to="/" className="text-sm text-blue-600 hover:underline">
            ← Back to dashboard
          </Link>
          <h2 className="text-2xl font-bold mt-2">
            Patient <span className="font-mono text-blue-600">{patientId}</span>
          </h2>
        </div>
        {latestPred && (
          <div className="text-right">
            <RiskBadge risk={latestPred.sepsis_risk} showPercent />
            <p className="text-xs text-slate-500 mt-1">
              Updated {formatRelativeTime(latestPred.predicted_at)} · model v
              {latestPred.model_version}
            </p>
          </div>
        )}
      </div>

      {/* Latest vitals summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-2 tabular">
        <VitalCard label="HR" value={latest.hr} unit="bpm" />
        <VitalCard label="O2Sat" value={latest.o2sat} unit="%" />
        <VitalCard label="Temp" value={latest.temp} unit="°C" />
        <VitalCard label="SBP" value={latest.sbp} unit="mmHg" />
        <VitalCard label="MAP" value={latest.map} unit="mmHg" />
        <VitalCard label="DBP" value={latest.dbp} unit="mmHg" />
        <VitalCard label="Resp" value={latest.resp} unit="bpm" />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <section className="bg-white rounded-lg border border-slate-200 p-4">
          <h3 className="font-semibold text-slate-700 text-sm uppercase tracking-wide mb-3">
            Sepsis risk timeline
          </h3>
          {predictions && predictions.length > 0 ? (
            <RiskTimeline predictions={predictions} threshold={threshold} />
          ) : (
            <p className="text-slate-500 text-sm py-12 text-center">No predictions yet.</p>
          )}
        </section>

        <section className="bg-white rounded-lg border border-slate-200 p-4">
          <h3 className="font-semibold text-slate-700 text-sm uppercase tracking-wide mb-3">
            Vital signs timeline
          </h3>
          <VitalsChart vitals={vitals} />
        </section>
      </div>

      {/* Recent vitals table */}
      <section className="bg-white rounded-lg border border-slate-200 overflow-hidden">
        <header className="px-4 py-3 border-b border-slate-200">
          <h3 className="font-semibold text-slate-700 text-sm uppercase tracking-wide">
            Recent measurements (last 10)
          </h3>
        </header>
        <div className="overflow-auto">
          <table className="w-full text-sm tabular">
            <thead className="bg-slate-50 text-slate-600 text-left">
              <tr>
                <th className="px-3 py-2 font-medium">Hour</th>
                <th className="px-3 py-2 font-medium">HR</th>
                <th className="px-3 py-2 font-medium">O2Sat</th>
                <th className="px-3 py-2 font-medium">Temp</th>
                <th className="px-3 py-2 font-medium">SBP</th>
                <th className="px-3 py-2 font-medium">MAP</th>
                <th className="px-3 py-2 font-medium">Resp</th>
                <th className="px-3 py-2 font-medium">Sepsis label</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {vitals.slice(-10).map((v) => (
                <tr key={v.hour} className="hover:bg-slate-50">
                  <td className="px-3 py-2 font-mono text-slate-700">{v.hour}</td>
                  <td className="px-3 py-2">{formatVital(v.hr, 0)}</td>
                  <td className="px-3 py-2">{formatVital(v.o2sat, 0)}</td>
                  <td className="px-3 py-2">{formatVital(v.temp, 1)}</td>
                  <td className="px-3 py-2">{formatVital(v.sbp, 0)}</td>
                  <td className="px-3 py-2">{formatVital(v.map, 0)}</td>
                  <td className="px-3 py-2">{formatVital(v.resp, 0)}</td>
                  <td className="px-3 py-2">
                    {v.sepsis_label === 1 ? (
                      <span className="inline-block px-2 py-0.5 bg-red-100 text-red-700 rounded text-xs font-semibold">
                        +
                      </span>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function VitalCard({
  label,
  value,
  unit,
}: {
  label: string;
  value: number | null;
  unit: string;
}) {
  return (
    <div className="bg-white border border-slate-200 rounded-md px-3 py-2">
      <div className="text-xs text-slate-500 uppercase">{label}</div>
      <div className="font-bold text-lg text-slate-800">
        {formatVital(value, label === "Temp" ? 1 : 0)}
        <span className="text-xs font-normal text-slate-400 ml-1">{unit}</span>
      </div>
    </div>
  );
}

