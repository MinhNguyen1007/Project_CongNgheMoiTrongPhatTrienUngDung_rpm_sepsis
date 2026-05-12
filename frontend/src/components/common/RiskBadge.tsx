// Badge hiển thị risk level. Color đồng bộ tailwind.config.js > theme.colors.risk.
import { formatRiskPercent, getRiskLevel } from "@/utils/formatters";

interface Props {
  risk: number;
  showPercent?: boolean;
  size?: "sm" | "md";
}

const LABELS = { low: "LOW", medium: "MEDIUM", high: "HIGH" } as const;
const STYLES = {
  low: "bg-green-100 text-green-700 ring-green-300",
  medium: "bg-yellow-100 text-yellow-800 ring-yellow-300",
  high: "bg-red-100 text-red-700 ring-red-300 animate-pulse",
} as const;

export function RiskBadge({ risk, showPercent = false, size = "md" }: Props) {
  const level = getRiskLevel(risk);
  const sizeCls = size === "sm" ? "text-xs px-2 py-0.5" : "text-sm px-2.5 py-1";

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full ring-1 font-semibold ${STYLES[level]} ${sizeCls}`}
    >
      {LABELS[level]}
      {showPercent && (
        <span className="tabular font-mono opacity-80">{formatRiskPercent(risk)}</span>
      )}
    </span>
  );
}
