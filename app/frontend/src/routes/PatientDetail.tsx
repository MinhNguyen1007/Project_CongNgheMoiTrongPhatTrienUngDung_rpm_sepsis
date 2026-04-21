import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Badge } from "@/components/ui/Badge";

interface TrendPoint {
  t: number;
  proba: number;
  label: string;
  alarm: boolean;
}

interface VitalPoint {
  t: number;
  label: string;
  hr: number | null;
  o2sat: number | null;
  resp: number | null;
  map: number | null;
}

interface TempPoint {
  t: number;
  label: string;
  temp: number | null;
}

function probaTone(p: number, thr: number): "ok" | "warn" | "critical" {
  if (p >= 0.5) return "critical";
  if (p >= thr) return "warn";
  return "ok";
}

export function PatientDetail() {
  const { patientId = "" } = useParams<{ patientId: string }>();

  const health = useQuery({ queryKey: ["health"], queryFn: api.health });

  // Server-backed proba history (persists across refresh)
  const { data: probaData, isLoading: probaLoading } = useQuery({
    queryKey: ["proba_history", patientId],
    queryFn: () => api.probaHistory(patientId),
    refetchInterval: 10_000,
    enabled: !!patientId,
  });

  // Server-backed vitals history
  const { data: vitalsData, isLoading: vitalsLoading } = useQuery({
    queryKey: ["vitals", patientId],
    queryFn: () => api.vitals(patientId, 72),
    refetchInterval: 10_000,
    enabled: !!patientId,
  });

  // Also fetch patient summary for header info
  const { data: patientsAll } = useQuery({
    queryKey: ["patients"],
    queryFn: api.patients,
    refetchInterval: 5_000,
  });
  const patient = patientsAll?.find((p) => p.patient_id === patientId);

  const threshold = health.data?.threshold ?? 0.05;

  // Build proba trend from server data
  const probaTrend = useMemo<TrendPoint[]>(() => {
    if (!probaData) return [];
    return probaData.map((p) => ({
      t: new Date(p.timestamp).getTime(),
      proba: p.proba,
      label: new Date(p.timestamp).toLocaleTimeString(),
      alarm: p.alarm,
    }));
  }, [probaData]);

  // Build vitals chart data (HR/Resp/MAP/SpO2 — temp scale too different, split below)
  const vitalsTrend = useMemo<VitalPoint[]>(() => {
    if (!vitalsData) return [];
    return vitalsData.map((v) => ({
      t: new Date(v.timestamp).getTime(),
      label: new Date(v.timestamp).toLocaleTimeString(),
      hr: v.hr,
      o2sat: v.o2sat,
      resp: v.resp,
      map: v.map,
    }));
  }, [vitalsData]);

  const tempTrend = useMemo<TempPoint[]>(() => {
    if (!vitalsData) return [];
    return vitalsData
      .filter((v) => v.temp !== null)
      .map((v) => ({
        t: new Date(v.timestamp).getTime(),
        label: new Date(v.timestamp).toLocaleTimeString(),
        temp: v.temp,
      }));
  }, [vitalsData]);

  const latestProba =
    probaTrend.length > 0 ? probaTrend[probaTrend.length - 1].proba : null;

  if (!patient && !probaLoading && probaTrend.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-slate-300 bg-white p-12 text-center">
        <p className="text-slate-600">
          Chưa có dữ liệu cho bệnh nhân <code>{patientId}</code>.
        </p>
        <Link to="/" className="mt-3 inline-block text-sky-700 hover:underline">
          ← Quay về danh sách
        </Link>
      </div>
    );
  }

  const tone = latestProba !== null ? probaTone(latestProba, threshold) : "ok";

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <Link to="/" className="text-sm text-slate-500 hover:text-slate-700">
            ← Danh sách
          </Link>
          <h2 className="mt-1 text-2xl font-semibold text-slate-900">
            {patientId}
          </h2>
          {patient && (
            <p className="text-sm text-slate-500">
              ICULOS {patient.iculos_hours}h · cập nhật{" "}
              {patient.last_update
                ? new Date(patient.last_update).toLocaleString()
                : "…"}
            </p>
          )}
        </div>
        {latestProba !== null && (
          <Badge tone={tone}>Proba {(latestProba * 100).toFixed(1)}%</Badge>
        )}
      </div>

      {/* Sepsis Probability Chart */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="mb-3 text-sm font-semibold text-slate-700">
          Xác suất sepsis theo thời gian
        </h3>
        {probaLoading ? (
          <div className="flex h-64 items-center justify-center text-sm text-slate-400">
            <div className="mr-2 h-5 w-5 animate-spin rounded-full border-2 border-slate-200 border-t-sky-600" />
            Đang tải...
          </div>
        ) : probaTrend.length < 2 ? (
          <div className="flex h-64 items-center justify-center text-sm text-slate-400">
            Cần ít nhất 2 điểm để vẽ. Đang chờ dữ liệu…
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={probaTrend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis
                domain={[0, 1]}
                tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                tick={{ fontSize: 11 }}
              />
              <Tooltip
                formatter={(v) =>
                  typeof v === "number" ? `${(v * 100).toFixed(1)}%` : String(v)
                }
              />
              <ReferenceLine
                y={threshold}
                stroke="#f59e0b"
                strokeDasharray="4 4"
                label={{
                  value: `thr ${threshold.toFixed(3)}`,
                  fontSize: 11,
                  fill: "#b45309",
                }}
              />
              <Line
                type="monotone"
                dataKey="proba"
                stroke="#dc2626"
                strokeWidth={2}
                dot={{ r: 3 }}
                name="Sepsis Probability"
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Vital Signs Chart */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="mb-3 text-sm font-semibold text-slate-700">
          Sinh hiệu theo thời gian
        </h3>
        {vitalsLoading ? (
          <div className="flex h-64 items-center justify-center text-sm text-slate-400">
            <div className="mr-2 h-5 w-5 animate-spin rounded-full border-2 border-slate-200 border-t-sky-600" />
            Đang tải vitals...
          </div>
        ) : vitalsTrend.length < 2 ? (
          <div className="flex h-64 items-center justify-center text-sm text-slate-400">
            Chưa có dữ liệu sinh hiệu.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={vitalsTrend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis
                yAxisId="hr"
                domain={[40, 180]}
                tick={{ fontSize: 11 }}
                label={{
                  value: "HR / Resp / MAP",
                  angle: -90,
                  position: "insideLeft",
                  fontSize: 10,
                }}
              />
              <YAxis
                yAxisId="spo2"
                orientation="right"
                domain={[80, 100]}
                tick={{ fontSize: 11 }}
                label={{
                  value: "SpO2",
                  angle: 90,
                  position: "insideRight",
                  fontSize: 10,
                }}
              />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line
                yAxisId="hr"
                type="monotone"
                dataKey="hr"
                stroke="#ef4444"
                strokeWidth={1.5}
                dot={false}
                name="HR"
                connectNulls
              />
              <Line
                yAxisId="hr"
                type="monotone"
                dataKey="resp"
                stroke="#8b5cf6"
                strokeWidth={1.5}
                dot={false}
                name="Resp"
                connectNulls
              />
              <Line
                yAxisId="hr"
                type="monotone"
                dataKey="map"
                stroke="#f59e0b"
                strokeWidth={1.5}
                dot={false}
                name="MAP"
                connectNulls
              />
              <Line
                yAxisId="spo2"
                type="monotone"
                dataKey="o2sat"
                stroke="#3b82f6"
                strokeWidth={1.5}
                dot={false}
                name="SpO2"
                connectNulls
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Temperature chart (separate — scale 35-41°C differs from HR) */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="mb-3 text-sm font-semibold text-slate-700">
          Nhiệt độ (°C)
        </h3>
        {vitalsLoading ? (
          <div className="flex h-40 items-center justify-center text-sm text-slate-400">
            <div className="mr-2 h-5 w-5 animate-spin rounded-full border-2 border-slate-200 border-t-sky-600" />
            Đang tải...
          </div>
        ) : tempTrend.length < 2 ? (
          <div className="flex h-40 items-center justify-center text-sm text-slate-400">
            Chưa có dữ liệu nhiệt độ.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={tempTrend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis
                domain={[35, 41]}
                tick={{ fontSize: 11 }}
                tickFormatter={(v) => `${v}°`}
              />
              <Tooltip
                formatter={(v) =>
                  typeof v === "number" ? `${v.toFixed(1)}°C` : String(v)
                }
              />
              <ReferenceLine
                y={38}
                stroke="#f59e0b"
                strokeDasharray="4 4"
                label={{ value: "sốt ≥38°", fontSize: 10, fill: "#b45309" }}
              />
              <ReferenceLine
                y={36}
                stroke="#3b82f6"
                strokeDasharray="4 4"
                label={{ value: "hạ thân ≤36°", fontSize: 10, fill: "#1d4ed8" }}
              />
              <Line
                type="monotone"
                dataKey="temp"
                stroke="#ea580c"
                strokeWidth={2}
                dot={{ r: 3 }}
                name="Temp"
                connectNulls
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      <p className="text-xs text-slate-400">
        Dữ liệu từ server, auto-refresh mỗi 10s. Chart persist sau khi refresh
        trang.
      </p>
    </div>
  );
}
