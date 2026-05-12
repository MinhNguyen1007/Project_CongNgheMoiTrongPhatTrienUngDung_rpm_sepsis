// Axios client + per-endpoint functions. Hook React Query gọi vào đây.
//
// WHY tách function-per-endpoint thay vì để hook gọi axios trực tiếp:
// - Type-safe (return type) + mock dễ trong test.
// - Hook chỉ lo cache/refetch, function lo URL/params.
import axios from "axios";
import type {
  AlertRecord,
  DriftReportRecord,
  ModelCurrentInfo,
  ModelInfo,
  PatientSummary,
  PredictionRecord,
  VitalRecord,
} from "@/types/api";

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  timeout: 10_000,
});

// ---- Patients ----
export async function fetchPatients(
  params: { hours_window?: number; limit?: number } = {}
): Promise<PatientSummary[]> {
  const { data } = await apiClient.get<PatientSummary[]>("/api/patients", { params });
  return data;
}

export async function fetchPatientVitals(
  patientId: string,
  limit = 24
): Promise<VitalRecord[]> {
  const { data } = await apiClient.get<VitalRecord[]>(
    `/api/patients/${patientId}/vitals`,
    { params: { limit } }
  );
  return data;
}

// ---- Predictions ----
export async function fetchPatientPredictions(
  patientId: string,
  limit = 100
): Promise<PredictionRecord[]> {
  const { data } = await apiClient.get<PredictionRecord[]>(
    `/api/predictions/${patientId}`,
    { params: { limit } }
  );
  return data;
}

export async function fetchAlerts(
  params: { threshold?: number; hours_window?: number } = {}
): Promise<AlertRecord[]> {
  const { data } = await apiClient.get<AlertRecord[]>("/api/predictions/alerts", {
    params,
  });
  return data;
}

// ---- Models ----
export async function fetchModelCurrentInfo(): Promise<ModelCurrentInfo> {
  const { data } = await apiClient.get<ModelCurrentInfo>("/api/models/current/info");
  return data;
}

export async function fetchModels(): Promise<ModelInfo[]> {
  const { data } = await apiClient.get<ModelInfo[]>("/api/models");
  return data;
}

// ---- Drift ----
export async function fetchDriftReports(limit = 10): Promise<DriftReportRecord[]> {
  const { data } = await apiClient.get<DriftReportRecord[]>("/api/drift/reports", {
    params: { limit },
  });
  return data;
}
