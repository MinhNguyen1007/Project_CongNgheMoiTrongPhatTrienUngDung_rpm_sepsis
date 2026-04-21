interface BadgeProps {
  tone: "ok" | "warn" | "critical" | "neutral";
  children: React.ReactNode;
}

const tones: Record<BadgeProps["tone"], string> = {
  ok: "bg-emerald-100 text-emerald-800 ring-emerald-200",
  warn: "bg-amber-100 text-amber-800 ring-amber-200",
  critical: "bg-red-600 text-white ring-red-700",
  neutral: "bg-slate-100 text-slate-700 ring-slate-200",
};

export function Badge({ tone, children }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${tones[tone]}`}
    >
      {children}
    </span>
  );
}
