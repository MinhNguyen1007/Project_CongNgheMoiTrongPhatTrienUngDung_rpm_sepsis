/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        // Medical UI: dùng system font cho neutral, tabular-nums cho số liệu.
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
      colors: {
        // Risk levels — đồng bộ với RiskBadge (xem CLAUDE.md).
        risk: {
          low: "#16a34a",     // green-600
          medium: "#eab308",  // yellow-500
          high: "#dc2626",    // red-600
        },
      },
    },
  },
  plugins: [],
};
