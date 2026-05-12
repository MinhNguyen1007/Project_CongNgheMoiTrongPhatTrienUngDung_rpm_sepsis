import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "@/components/layout/Layout";
import Dashboard from "@/pages/Dashboard";
import DriftReports from "@/pages/DriftReports";
import ModelInfo from "@/pages/ModelInfo";
import PatientDetail from "@/pages/PatientDetail";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="patients/:patientId" element={<PatientDetail />} />
        <Route path="models" element={<ModelInfo />} />
        <Route path="drift" element={<DriftReports />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
