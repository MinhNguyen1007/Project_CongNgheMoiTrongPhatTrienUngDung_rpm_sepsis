// React Query wrappers cho patient + vital endpoints.
import { useQuery } from "@tanstack/react-query";

import { fetchPatientVitals, fetchPatients } from "@/api/client";

export function usePatients(params: { hours_window?: number; limit?: number } = {}) {
  return useQuery({
    queryKey: ["patients", params],
    queryFn: () => fetchPatients(params),
    refetchInterval: 15_000, // safety net nếu WS bị disconnect
  });
}

export function usePatientVitals(patientId: string | undefined, limit = 24) {
  return useQuery({
    queryKey: ["patient-vitals", patientId, limit],
    queryFn: () => fetchPatientVitals(patientId!, limit),
    enabled: !!patientId,
  });
}
