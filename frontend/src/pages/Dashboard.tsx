import { AlertPanel } from "@/components/alerts/AlertPanel";
import { PatientList } from "@/components/patients/PatientList";
import { StatsCards } from "@/components/dashboard/StatsCards";

export default function Dashboard() {
  return (
    <div className="space-y-5 max-w-7xl mx-auto">
      <StatsCards />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 space-y-3">
          <h3 className="text-sm font-semibold text-slate-600 uppercase tracking-wide">
            Patients (sorted by risk)
          </h3>
          <PatientList />
        </div>

        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-slate-600 uppercase tracking-wide">
            Live Alerts
          </h3>
          <AlertPanel />
        </div>
      </div>
    </div>
  );
}
