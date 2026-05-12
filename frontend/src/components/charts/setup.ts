// Chart.js component registration — phải import 1 lần TRƯỚC khi render chart.
// WHY tách file: react-chartjs-2 v5 không auto-register để giảm bundle size.
// Mọi chart import file này (side-effect) thay vì register trong từng component.
import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Title,
  Tooltip,
} from "chart.js";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
);
