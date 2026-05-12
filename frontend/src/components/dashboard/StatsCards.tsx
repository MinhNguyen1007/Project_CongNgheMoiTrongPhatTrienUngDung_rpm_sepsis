import { usePatients } from "@/hooks/usePatients";
import { useAlerts } from "@/hooks/useAlerts";
import { useModelCurrentInfo } from "@/hooks/useModelInfo";
import { getRiskLevel } from "@/utils/formatters";

interface CardProps {
  label: string;
  value: string | number;
  hint?: string;
  accent?: "blue" | "red" | "green" | "slate";
}

const ACCENTS = {
  blue: "border-l-blue-500",
  red: "border-l-red-500",
  green: "border-l-green-500",
  slate: "border-l-slate-400",
} as const;

function Card({ label, value, hint, accent = "slate" }: CardProps) {
  return (
    <div className={`bg-white rounded-lg border border-slate-200 border-l-4 ${ACCENTS[accent]} px-4 py-3`}>
      <div className="text-xs text-slate-500 uppercase tracking-wide">{label}</div>
      <div className="mt-1 text-2xl font-bold tabular text-slate-800">{value}</div>
      {hint && <div className="text-xs text-slate-500 mt-0.5">{hint}</div>}
    </div>
  );
}

export function StatsCards() {
  const { data: patients } = usePatients();
  const { data: alerts } = useAlerts();
  const { data: modelInfo } = useModelCurrentInfo();

  const total = patients?.length ?? 0;
  const highRisk = patients?.filter((p) => getRiskLevel(p.current_risk) === "high").length ?? 0;
  const mediumRisk =
    patients?.filter((p) => getRiskLevel(p.current_risk) === "medium").length ?? 0;
  const alertCount = alerts?.length ?? 0;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
      <Card label="Active patients (24h)" value={total} accent="blue" />
      <Card label="High risk" value={highRisk} accent="red" hint={`Risk ≥ ${modelInfo?.threshold.toFixed(2) ?? "0.70"}`} />
      <Card label="Medium risk" value={mediumRisk} accent="slate" hint="0.30 ≤ Risk < 0.70" />
      <Card label="Active alerts" value={alertCount} accent="red" hint="From /alerts endpoint" />
    </div>
  );
}
