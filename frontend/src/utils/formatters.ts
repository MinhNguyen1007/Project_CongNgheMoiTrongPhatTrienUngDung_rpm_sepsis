// Formatting helpers — single source cho UI text.
import { formatDistanceToNow, parseISO } from "date-fns";
import type { RiskLevel } from "@/types/api";

// Risk level derived. Threshold 0.7 từ MODEL_THRESHOLD trong backend.
// Hạ < 0.3 = low (xanh), 0.3-0.7 = medium (vàng), >= 0.7 = high (đỏ).
// Đồng bộ với CLAUDE.md frontend RiskBadge spec.
export function getRiskLevel(risk: number): RiskLevel {
  if (risk >= 0.7) return "high";
  if (risk >= 0.3) return "medium";
  return "low";
}

export function formatRisk(risk: number): string {
  // 2 chữ số sau dấu phẩy đủ cho UI (0.94 thay vì 0.9421...).
  return risk.toFixed(2);
}

export function formatRiskPercent(risk: number): string {
  return `${(risk * 100).toFixed(0)}%`;
}

export function formatRelativeTime(iso: string): string {
  try {
    return formatDistanceToNow(parseISO(iso), { addSuffix: true });
  } catch {
    return iso;
  }
}

export function formatGender(gender: number | null): string {
  if (gender === null) return "—";
  return gender === 1 ? "Male" : "Female";
}

export function formatAge(age: number | null): string {
  if (age === null) return "—";
  return Math.round(age).toString();
}

export function formatVital(v: number | null, digits = 1): string {
  if (v === null || Number.isNaN(v)) return "—";
  return v.toFixed(digits);
}
