import { useAuthStore } from "@/stores/authStore";
import type {
  AlertRecord,
  HealthResponse,
  LoginRequest,
  PatientSummary,
  PredictRequest,
  PredictResponse,
  ProbaPoint,
  RegisterRequest,
  TokenResponse,
  UserResponse,
  UserUpdateRequest,
  VitalRecord,
} from "@/types/api";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

function authHeaders(): Record<string, string> {
  const token = useAuthStore.getState().token;
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (res.status === 401) {
    // Token expired or invalid — logout
    useAuthStore.getState().logout();
  }
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  // ── Health ──
  health: () => request<HealthResponse>("/health"),

  // ── Predict ──
  predict: (req: PredictRequest) =>
    request<PredictResponse>("/predict", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  // ── Patients ──
  patients: () => request<PatientSummary[]>("/patients"),

  vitals: (patientId: string, hours = 72) =>
    request<VitalRecord[]>(`/patients/${patientId}/vitals?hours=${hours}`),

  probaHistory: (patientId: string) =>
    request<ProbaPoint[]>(`/patients/${patientId}/proba_history`),

  // ── Auth ──
  login: (req: LoginRequest) =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  me: () => request<UserResponse>("/auth/me"),

  // ── User management (admin only on backend) ──
  listUsers: () => request<UserResponse[]>("/auth/users"),

  registerUser: (req: RegisterRequest) =>
    request<UserResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  updateUser: (id: number, req: UserUpdateRequest) =>
    request<UserResponse>(`/auth/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(req),
    }),

  deleteUser: (id: number) =>
    fetch(`${BASE_URL}/auth/users/${id}`, {
      method: "DELETE",
      headers: authHeaders(),
    }).then((res) => {
      if (res.status === 401) useAuthStore.getState().logout();
      if (!res.ok && res.status !== 204)
        throw new Error(`${res.status} ${res.statusText}`);
    }),

  // ── Alerts (persisted) ──
  alerts: (params?: {
    patient_id?: string;
    acknowledged?: boolean;
    limit?: number;
  }) => {
    const query = new URLSearchParams();
    if (params?.patient_id) query.set("patient_id", params.patient_id);
    if (params?.acknowledged !== undefined)
      query.set("acknowledged", String(params.acknowledged));
    if (params?.limit) query.set("limit", String(params.limit));
    const qs = query.toString();
    return request<AlertRecord[]>(`/alerts${qs ? `?${qs}` : ""}`);
  },

  acknowledgeAlert: (alertId: number) =>
    request<AlertRecord>(`/alerts/${alertId}/acknowledge`, { method: "PUT" }),
};
