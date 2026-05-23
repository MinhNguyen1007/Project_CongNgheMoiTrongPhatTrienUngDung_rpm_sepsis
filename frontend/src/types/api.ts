// TypeScript types — KHỚP 1:1 với backend/app/schemas.py (Pydantic).
// Khi backend schema thay đổi, file này phải sync theo.

export interface PatientSummary {
  id: string;
  age: number | null;
  gender: 0 | 1 | null;
  current_risk: number;
  last_updated: string; // ISO datetime
}

export interface VitalRecord {
  hour: number;
  hr: number | null;
  o2sat: number | null;
  temp: number | null;
  sbp: number | null;
  map: number | null;
  dbp: number | null;
  resp: number | null;
  etco2: number | null;
  lab_values: Record<string, number | null> | null;
  sepsis_label: number | null;
  is_validated: boolean;
  created_at: string;
}

export interface PredictionRecord {
  hour: number;
  sepsis_risk: number;
  model_version: string;
  predicted_at: string;
}

export interface AlertRecord {
  patient_id: string;
  hour: number;
  sepsis_risk: number;
  predicted_at: string;
}

export interface ModelInfo {
  version: string;
  mlflow_run_id: string;
  auroc: number | null;
  auprc: number | null;
  utility: number | null;
  threshold: number | null;
  model_type: string | null;
  status: string;
  created_at: string;
}

export interface ModelCurrentInfo {
  version: string;
  threshold: number;
  n_features: number;
}

export interface DriftReportRecord {
  id: number;
  ref_period_start: string;
  ref_period_end: string;
  target_period_start: string;
  target_period_end: string;
  drift_share: number;
  triggered_retrain: boolean;
  created_at: string;
}

// WebSocket event — match backend WSPredictionEvent schema.
export interface WSPredictionEvent {
  type: "prediction";
  patient_id: string;
  hour: number;
  sepsis_risk: number;
  alert: boolean;
  model_version: string;
  predicted_at: string;
}

// Risk level — derived từ sepsis_risk + threshold trong UI (KHÔNG có ở backend).
export type RiskLevel = "low" | "medium" | "high";
