// Types mirror app/backend/schemas.py. Keep in sync if backend changes.

export interface HealthResponse {
  status: string;
  model_uri: string;
  feature_count: number;
  threshold: number;
  min_consecutive: number;
  warmup_hours: number;
}

export interface PredictRequest {
  patient_id: string;
  iculos_hours: number;
  features: Record<string, number>;
}

export interface PredictResponse {
  patient_id: string;
  timestamp: string;
  proba: number;
  alarm: boolean;
  threshold: number;
  consecutive_above: number;
  warmup_muted: boolean;
}

export interface AlertEvent {
  event: "alert";
  patient_id: string;
  timestamp: string;
  proba: number;
  iculos_hours: number;
}

// Server-side patient summary — served by GET /patients
export interface PatientSummary {
  patient_id: string;
  latest_proba: number;
  latest_alarm: boolean;
  last_update: string;
  iculos_hours: number;
}

// Vital-signs snapshot — served by GET /patients/{id}/vitals
export interface VitalRecord {
  timestamp: string;
  hr: number | null;
  o2sat: number | null;
  temp: number | null;
  sbp: number | null;
  map: number | null;
  dbp: number | null;
  resp: number | null;
  iculos_hours: number;
}

// Proba timeline point — served by GET /patients/{id}/proba_history
export interface ProbaPoint {
  timestamp: string;
  proba: number;
  alarm: boolean;
  streak: number;
}

// ── Auth types ─────────────────────────────────────────

export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export type UserRole = "admin" | "doctor" | "viewer";

export interface UserResponse {
  id: number;
  username: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
}

export interface RegisterRequest {
  username: string;
  password: string;
  full_name?: string;
  role?: UserRole;
}

export interface UserUpdateRequest {
  full_name?: string;
  role?: UserRole;
  is_active?: boolean;
  password?: string;
}

// ── Alert persistence types ───────────────────────────

export interface AlertRecord {
  id: number;
  patient_id: string;
  timestamp: string;
  proba: number;
  iculos_hours: number;
  consecutive_above: number;
  acknowledged: boolean;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
}
