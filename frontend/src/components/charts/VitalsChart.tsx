// Multi-axis line chart: HR, O2Sat, Temp, Resp cùng lúc.
// WHY hiển thị 4 cái: bác sĩ cần thấy correlation (HR tăng + O2 giảm + Resp
// tăng = early sepsis signal).
// WHY 2 trục Y: HR/SBP scale khác Temp/O2Sat → tách trục để không bị nén.
import "@/components/charts/setup";

import { Line } from "react-chartjs-2";
import type { ChartOptions } from "chart.js";
import type { VitalRecord } from "@/types/api";

interface Props {
  vitals: VitalRecord[];
}

// WHY spanGaps=true: data có NaN giữa các giờ → vẫn nối line, không vẽ thành
// nhiều đoạn rời.
const baseOptions: ChartOptions<"line"> = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: "index", intersect: false },
  plugins: {
    legend: { position: "top", labels: { boxWidth: 12, padding: 12 } },
    tooltip: { backgroundColor: "rgba(15,23,42,0.95)" },
  },
  scales: {
    x: {
      title: { display: true, text: "ICU hour (ICULOS)" },
      grid: { color: "rgba(0,0,0,0.05)" },
    },
    yRate: {
      type: "linear",
      position: "left",
      title: { display: true, text: "HR / Resp (bpm)" },
      grid: { color: "rgba(0,0,0,0.05)" },
    },
    yPct: {
      type: "linear",
      position: "right",
      min: 80,
      max: 105,
      title: { display: true, text: "O2Sat (%) / Temp (°C)" },
      grid: { drawOnChartArea: false },
    },
  },
};

export function VitalsChart({ vitals }: Props) {
  const labels = vitals.map((v) => v.hour);
  const data = {
    labels,
    datasets: [
      {
        label: "HR",
        data: vitals.map((v) => v.hr),
        borderColor: "#dc2626", // red-600
        backgroundColor: "rgba(220,38,38,0.05)",
        yAxisID: "yRate",
        spanGaps: true,
        tension: 0.2,
        pointRadius: 2,
      },
      {
        label: "Resp",
        data: vitals.map((v) => v.resp),
        borderColor: "#16a34a", // green-600
        backgroundColor: "rgba(22,163,74,0.05)",
        yAxisID: "yRate",
        spanGaps: true,
        tension: 0.2,
        pointRadius: 2,
      },
      {
        label: "O2Sat",
        data: vitals.map((v) => v.o2sat),
        borderColor: "#2563eb", // blue-600
        backgroundColor: "rgba(37,99,235,0.05)",
        yAxisID: "yPct",
        spanGaps: true,
        tension: 0.2,
        pointRadius: 2,
      },
      {
        label: "Temp",
        data: vitals.map((v) => v.temp),
        borderColor: "#ea580c", // orange-600
        backgroundColor: "rgba(234,88,12,0.05)",
        yAxisID: "yPct",
        spanGaps: true,
        tension: 0.2,
        pointRadius: 2,
      },
    ],
  };

  return (
    <div className="h-80">
      <Line data={data} options={baseOptions} />
    </div>
  );
}
