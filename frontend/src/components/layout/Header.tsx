import { useModelCurrentInfo } from "@/hooks/useModelInfo";
import { useWebSocketStatus } from "@/context/WebSocketContext";
import { MenuIcon } from "@/components/common/Icons";

const STATUS_STYLES = {
  open: "bg-green-100 text-green-700 ring-green-300",
  connecting: "bg-yellow-100 text-yellow-700 ring-yellow-300",
  closed: "bg-red-100 text-red-700 ring-red-300",
} as const;

const STATUS_LABELS = {
  open: "Live",
  connecting: "Connecting",
  closed: "Disconnected",
} as const;

interface HeaderProps {
  onMenuClick: () => void;
}

export function Header({ onMenuClick }: HeaderProps) {
  const wsStatus = useWebSocketStatus();
  const { data: modelInfo } = useModelCurrentInfo();

  return (
    <header className="h-14 bg-white border-b border-slate-200 px-4 lg:px-6 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onMenuClick}
          className="lg:hidden p-1.5 rounded-md text-slate-600 hover:bg-slate-100"
        >
          <MenuIcon className="w-5 h-5" />
        </button>
        <h2 className="font-semibold text-slate-800">ICU Sepsis Monitoring</h2>
      </div>
      <div className="flex items-center gap-3 text-sm">
        {modelInfo && (
          <span className="text-slate-500">
            Model{" "}
            <code className="bg-slate-100 px-1.5 py-0.5 rounded text-slate-700">
              v{modelInfo.version}
            </code>{" "}
            · thr{" "}
            <span className="tabular font-mono">{modelInfo.threshold.toFixed(2)}</span>
          </span>
        )}
        <span
          className={`inline-flex items-center gap-1.5 rounded-full ring-1 px-2.5 py-0.5 text-xs font-semibold ${STATUS_STYLES[wsStatus]}`}
        >
          <span
            className={`h-2 w-2 rounded-full ${
              wsStatus === "open" ? "bg-green-500 animate-pulse" : "bg-current"
            }`}
          />
          {STATUS_LABELS[wsStatus]}
        </span>
      </div>
    </header>
  );
}
