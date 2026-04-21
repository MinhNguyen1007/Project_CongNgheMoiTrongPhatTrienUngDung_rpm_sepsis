import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useAlertStream } from "@/hooks/useAlertStream";
import { usePatientsStore } from "@/stores/patientsStore";
import { useAuthStore } from "@/stores/authStore";
import { useEffect } from "react";
import { Badge } from "@/components/ui/Badge";

const navItem =
  "px-3 py-2 rounded-md text-sm font-medium text-slate-600 hover:bg-slate-100";
const navItemActive = "bg-slate-900 text-white hover:bg-slate-900";

export function AppLayout() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 15_000,
  });
  const { events, status, lastEvent } = useAlertStream();
  const ingest = usePatientsStore((s) => s.ingestAlert);
  const { username, role, logout } = useAuthStore();
  const navigate = useNavigate();

  useEffect(() => {
    if (lastEvent) ingest(lastEvent);
  }, [lastEvent, ingest]);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const wsTone =
    status === "open" ? "ok" : status === "connecting" ? "warn" : "critical";
  const apiTone = health.isSuccess ? "ok" : health.isError ? "critical" : "warn";

  return (
    <div className="min-h-full">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-6">
            <h1 className="text-lg font-semibold text-slate-900">
              Sepsis Early-Warning
            </h1>
            <nav className="flex gap-1">
              <NavLink
                to="/"
                end
                className={({ isActive }) =>
                  `${navItem} ${isActive ? navItemActive : ""}`
                }
              >
                Bệnh nhân
              </NavLink>
              <NavLink
                to="/alerts"
                className={({ isActive }) =>
                  `${navItem} ${isActive ? navItemActive : ""}`
                }
              >
                Cảnh báo ({events.length})
              </NavLink>
              {role === "admin" && (
                <NavLink
                  to="/admin"
                  className={({ isActive }) =>
                    `${navItem} ${isActive ? navItemActive : ""}`
                  }
                >
                  Quản trị
                </NavLink>
              )}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-xs">
              <Badge tone={apiTone}>
                API {health.isSuccess ? "OK" : health.isError ? "ERR" : "…"}
              </Badge>
              <Badge tone={wsTone}>WS {status}</Badge>
              {health.data && (
                <span className="hidden text-slate-500 sm:inline">
                  thr={health.data.threshold.toFixed(3)} · k=
                  {health.data.min_consecutive}
                </span>
              )}
            </div>
            <div className="ml-2 flex items-center gap-2 border-l border-slate-200 pl-3">
              <span className="text-sm text-slate-600">
                {username}
                {role === "admin" && (
                  <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-amber-700">
                    admin
                  </span>
                )}
              </span>
              <button
                onClick={handleLogout}
                className="rounded-md px-2 py-1 text-xs font-medium text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
              >
                Đăng xuất
              </button>
            </div>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
