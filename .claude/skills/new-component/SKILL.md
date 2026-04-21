---
name: new-component
description: Scaffold một React component mới trong app/frontend (TypeScript + Tailwind) với test. Dùng khi thêm phần UI cho dashboard như patient card, vital chart, alert panel.
---

# Skill: New React Component

Tạo React component TypeScript mới theo convention của dashboard bác sĩ. Ưu tiên functional component + hooks.

## Quy trình

1. Hỏi user (nếu chưa rõ):
   - Tên component (PascalCase, vd `PatientVitalChart`)
   - Loại: presentational (chỉ render props) / container (fetch data) / layout
   - Props chính (tên + type)
2. Chọn folder phù hợp trong `app/frontend/src/`:
   - `components/patients/`, `components/alerts/`, `components/charts/`, v.v.
3. Tạo file `ComponentName.tsx` + `ComponentName.test.tsx` + (tuỳ) `index.ts`.
4. Dùng TailwindCSS cho styling. Màu alert = đỏ (Tailwind `red-500/600`), bình thường = neutral.
5. Nếu fetch data, dùng TanStack Query. Nếu realtime, subscribe WebSocket qua hook `useWebSocket`.
6. Thêm test bằng `vitest` + `@testing-library/react`.
7. Chạy `npm test -- <ComponentName>` để verify.

## Cấu trúc frontend

```
app/frontend/
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── routes/               # react-router pages
│   ├── components/
│   │   ├── patients/
│   │   ├── alerts/
│   │   ├── charts/
│   │   └── ui/               # atomic: Button, Input, Card
│   ├── hooks/                # useWebSocket, useAuth
│   ├── api/                  # TanStack Query fetchers
│   ├── stores/               # Zustand
│   └── types/                # shared types
└── vite.config.ts
```

## Template component

```tsx
import { useEffect, useState } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";

interface PatientVitalChartProps {
  patientId: string;
  hoursBack?: number;
}

interface VitalPoint {
  ts: string;
  hr: number;
  spo2: number;
  temp: number;
  probability?: number;
}

export function PatientVitalChart({
  patientId,
  hoursBack = 24,
}: PatientVitalChartProps) {
  const [history, setHistory] = useState<VitalPoint[]>([]);
  const { lastMessage } = useWebSocket(`/ws/patients/${patientId}`);

  useEffect(() => {
    fetch(`/api/patients/${patientId}/vitals?hours=${hoursBack}`)
      .then((r) => r.json())
      .then(setHistory);
  }, [patientId, hoursBack]);

  useEffect(() => {
    if (lastMessage)
      setHistory((prev) => [...prev, lastMessage as VitalPoint].slice(-500));
  }, [lastMessage]);

  const latestProb = history.at(-1)?.probability ?? 0;
  const alertLevel =
    latestProb > 0.7 ? "critical" : latestProb > 0.5 ? "warning" : "ok";

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">BN {patientId}</h3>
        <span
          className={`rounded px-2 py-1 text-sm font-medium ${
            alertLevel === "critical"
              ? "bg-red-600 text-white"
              : alertLevel === "warning"
                ? "bg-yellow-500 text-white"
                : "bg-green-100 text-green-800"
          }`}
        >
          {(latestProb * 100).toFixed(1)}%
        </span>
      </div>
      {/* TODO: Recharts LineChart cho HR, SpO2, Temp */}
    </div>
  );
}
```

## Template test

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { PatientVitalChart } from "./PatientVitalChart";

vi.mock("@/hooks/useWebSocket", () => ({
  useWebSocket: () => ({ lastMessage: null }),
}));

describe("PatientVitalChart", () => {
  it("renders patient ID", () => {
    render(<PatientVitalChart patientId="P001" />);
    expect(screen.getByText(/BN P001/)).toBeInTheDocument();
  });
});
```

## Lưu ý

- **Accessibility:** `aria-label` cho icon-only button, `role="alert"` cho cảnh báo nghiêm trọng.
- **Props:** dùng `interface`, không `type =` (dễ extend hơn).
- **Style:** chỉ Tailwind, không CSS file riêng trừ animation phức tạp.
- **State:** component state cho UI, Zustand cho cross-component, TanStack cho server state.
- **Format số sinh tồn:** HR (bpm), SpO2 (%), Temp (°C), giữ 1 chữ số thập phân.
