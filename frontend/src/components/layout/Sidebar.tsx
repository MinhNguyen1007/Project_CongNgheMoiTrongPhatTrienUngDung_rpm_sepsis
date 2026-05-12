import { NavLink } from "react-router-dom";

import { useAlertsContext } from "@/context/AlertsContext";

interface NavItem {
  to: string;
  label: string;
  icon: string;
}

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: "🏥" },
  { to: "/models", label: "Model Registry", icon: "🤖" },
  { to: "/drift", label: "Drift Reports", icon: "📊" },
];

export function Sidebar() {
  const { unreadCount } = useAlertsContext();

  return (
    <aside className="w-56 bg-slate-900 text-slate-100 flex flex-col">
      <div className="px-5 py-5 border-b border-slate-700">
        <h1 className="font-bold text-lg leading-tight">Sepsis EW</h1>
        <p className="text-xs text-slate-400 mt-1">Patient Monitoring</p>
      </div>
      <nav className="flex-1 px-2 py-4 space-y-1">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              `flex items-center justify-between px-3 py-2 rounded-md text-sm transition-colors ${
                isActive
                  ? "bg-blue-600 text-white"
                  : "text-slate-300 hover:bg-slate-800 hover:text-white"
              }`
            }
          >
            <span className="flex items-center gap-2">
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </span>
            {item.to === "/" && unreadCount > 0 && (
              <span className="bg-red-600 text-white text-xs font-bold rounded-full px-2 py-0.5">
                {unreadCount}
              </span>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="px-5 py-3 border-t border-slate-700 text-xs text-slate-400">
        v0.1.0 · MLflow
      </div>
    </aside>
  );
}
