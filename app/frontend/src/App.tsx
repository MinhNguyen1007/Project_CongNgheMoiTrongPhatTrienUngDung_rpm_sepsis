import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppLayout } from "@/components/AppLayout";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { RoleGate } from "@/components/RoleGate";
import { Login } from "@/routes/Login";
import { PatientList } from "@/routes/PatientList";
import { PatientDetail } from "@/routes/PatientDetail";
import { AlertsFeed } from "@/routes/AlertsFeed";
import { AdminSettings } from "@/routes/AdminSettings";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            element={
              <ProtectedRoute>
                <AppLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<PatientList />} />
            <Route path="/patients/:patientId" element={<PatientDetail />} />
            <Route path="/alerts" element={<AlertsFeed />} />
            <Route
              path="/admin"
              element={
                <RoleGate allow={["admin"]}>
                  <AdminSettings />
                </RoleGate>
              }
            />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
