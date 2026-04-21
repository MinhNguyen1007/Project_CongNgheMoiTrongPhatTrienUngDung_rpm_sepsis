import { create } from "zustand";
import type { AlertEvent, PatientSummary } from "@/types/api";

interface PatientsState {
  patients: Record<string, PatientSummary>;
  ingestAlert: (event: AlertEvent) => void;
  list: () => PatientSummary[];
}

// Backend doesn't yet expose /patients. We track what we observe on the alert
// stream — good enough for the demo dashboard until we wire the consumer.
export const usePatientsStore = create<PatientsState>((set, get) => ({
  patients: {},
  ingestAlert: (event) =>
    set((state) => ({
      patients: {
        ...state.patients,
        [event.patient_id]: {
          patient_id: event.patient_id,
          latest_proba: event.proba,
          latest_alarm: true,
          last_update: event.timestamp,
          iculos_hours: event.iculos_hours,
        },
      },
    })),
  list: () =>
    Object.values(get().patients).sort(
      (a, b) => b.latest_proba - a.latest_proba,
    ),
}));
