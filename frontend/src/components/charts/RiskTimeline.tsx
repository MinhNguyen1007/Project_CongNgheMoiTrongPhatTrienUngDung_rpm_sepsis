// Line chart sepsis_risk theo hour + đường threshold ngang.
//
// WHY area fill: vùng dưới line = "risk hiện tại", trực quan tăng/giảm hơn
// line trần. Màu thay đổi theo level cuối cùng (high=đỏ, medium=vàng, low=xanh).
import "@/components/charts/setup";

import { Line } from "react-chartjs-2";
import type { ChartOptions } from "chart.js";
import type { PredictionRecord } from "@/types/api";

interface Props {
  predictions: PredictionRecord[];
  threshold: number;
}

const options: ChartOptions<"line"> = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: "index", intersect: false },
  plugins: {
    legend: { position: "top", labels: { boxWidth: 12, padding: 12 } },
    tooltip: {
      backgroundColor: "rgba(15,23,42,0.95)",
      callbacks: {
        label: (ctx) => `${ctx.dataset.label}: ${(ctx.parsed.y as number).toFixed(3)}`,
      },
    },
  },
  scales: {
    x: { title: { display: true, text: "ICU hour" } },
    y: {
      min: 0,
      max: 1,
      title: { display: true, text: "Sepsis risk" },
      grid: { color: "rgba(0,0,0,0.05)" },
    },
  },
};

export function RiskTimeline({ predictions, threshold }: Props) {
  const labels = predictions.map((p) => p.hour);
  const data = {
    labels,
    datasets: [
      {
        label: "Sepsis risk",
        data: predictions.map((p) => p.sepsis_risk),
        borderColor: "#2563eb",
        backgroundColor: "rgba(37,99,235,0.12)",
        fill: true,
        tension: 0.25,
        pointRadius: 0,
        pointHoverRadius: 4,
      },
      {
        label: `Threshold (${threshold.toFixed(2)})`,
        data: labels.map(() => threshold),
        borderColor: "#dc2626",
        borderDash: [6, 4],
        borderWidth: 1.5,
        pointRadius: 0,
        fill: false,
      },
    ],
  };

  return (
    <div className="h-72">
      <Line data={data} options={options} />
    </div>
  );
}
