import { useQuery } from "@tanstack/react-query";

import { fetchDriftReports, fetchModelCurrentInfo, fetchModels } from "@/api/client";

export function useModelCurrentInfo() {
  return useQuery({
    queryKey: ["model-current"],
    queryFn: fetchModelCurrentInfo,
    staleTime: 60_000,
  });
}

export function useModels() {
  return useQuery({
    queryKey: ["models"],
    queryFn: fetchModels,
  });
}

export function useDriftReports(limit = 10) {
  return useQuery({
    queryKey: ["drift-reports", limit],
    queryFn: () => fetchDriftReports(limit),
  });
}
