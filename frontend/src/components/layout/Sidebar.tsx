import { NavLink } from "react-router-dom";

import { useAlertsContext } from "@/context/AlertsContext";
import { CloseIcon, DashboardIcon, DriftIcon, ModelIcon } from "@/components/common/Icons";

interface NavItem {
  to: string;
  label: string;
  icon: React.FC<{ className?: string }>;
}

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: DashboardIcon },
  { to: "/models", label: "Model Registry", icon: ModelIcon },
  { to: "/drift", label: "Drift Reports", icon: DriftIcon },
];

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

export function Sidebar({ open, onClose }: SidebarProps) {
  const { unreadCount } = useAlertsContext();

  return (
    <>
      {/* Mobile backdrop */}
      {open && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 w-56 bg-slate-900 text-slate-100 flex flex-col transform transition-transform duration-200 ease-in-out lg:static lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="px-5 py-5 border-b border-slate-700 flex items-center justify-between">
          <div>
            <h1 className="font-bold text-lg leading-tight">Sepsis EW</h1>
            <p className="text-xs text-slate-400 mt-1">Patient Monitoring</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="lg:hidden text-slate-400 hover:text-white"
          >
            <CloseIcon className="w-5 h-5" />
          </button>
        </div>
        <nav className="flex-1 px-2 py-4 space-y-1">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              onClick={onClose}
              className={({ isActive }) =>
                `flex items-center justify-between px-3 py-2 rounded-md text-sm transition-colors ${
                  isActive
                    ? "bg-blue-600 text-white"
                    : "text-slate-300 hover:bg-slate-800 hover:text-white"
                }`
              }
            >
              <span className="flex items-center gap-2">
                <item.icon className="w-5 h-5" />
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
    </>
  );
}
