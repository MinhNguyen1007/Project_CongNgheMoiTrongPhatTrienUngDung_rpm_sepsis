// React Query hook cho /api/predictions/alerts. KHÁC `useAlertsContext`:
// - useAlertsContext: in-memory queue từ WS, mới nhất ở đầu.
// - useAlerts (đây): server-truth, dùng cho dashboard count.
import { useQuery } from "@tanstack/react-query";

import { fetchAlerts, fetchPatientPredictions } from "@/api/client";

export function useAlerts(params: { threshold?: number; hours_window?: number } = {}) {
  return useQuery({
    queryKey: ["alerts", params],
    queryFn: () => fetchAlerts(params),
    refetchInterval: 15_000,
  });
}

export function usePatientPredictions(patientId: string | undefined, limit = 100) {
  return useQuery({
    queryKey: ["patient-predictions", patientId, limit],
    queryFn: () => fetchPatientPredictions(patientId!, limit),
    enabled: !!patientId,
  });
}
