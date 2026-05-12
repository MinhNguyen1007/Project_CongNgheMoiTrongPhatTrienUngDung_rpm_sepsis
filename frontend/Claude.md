# Frontend - CLAUDE.md

> Đọc `../CLAUDE.md` trước. File này chỉ chi tiết riêng cho frontend.

## Trách nhiệm

1. Dashboard: list patients + alert panel + stats cards
2. Patient detail: vital signs timeline + risk timeline (Chart.js)
3. Real-time updates qua WebSocket
4. Model info page, drift reports page

## Tech

React 18 + TypeScript + Vite + TailwindCSS + Chart.js (react-chartjs-2) + TanStack Query + Axios + React Router

## Cấu trúc

```
frontend/src/
├── main.tsx               # Mount App + providers (QueryClient, WebSocket, Alerts)
├── App.tsx                # Router
├── api/                   # axios calls: patients, predictions, models, drift
├── hooks/
│   ├── useWebSocket.ts    # Custom hook: auto reconnect, heartbeat
│   ├── usePatients.ts     # React Query wrappers
│   └── useAlerts.ts
├── pages/
│   ├── Dashboard.tsx      # Patient list + alerts
│   ├── PatientDetail.tsx  # Vitals + risk charts
│   ├── ModelInfo.tsx
│   └── DriftReports.tsx
├── components/
│   ├── layout/            # Sidebar, Header, Layout
│   ├── patients/          # PatientCard, PatientList, RiskBadge
│   ├── charts/            # VitalsChart, RiskTimeline
│   ├── alerts/            # AlertPanel
│   └── common/            # Loading, ErrorBoundary, EmptyState
├── context/
│   ├── WebSocketContext.tsx
│   └── AlertsContext.tsx
├── types/                 # TS types match Pydantic schemas
└── utils/                 # formatters, constants
```

## Key implementations

**`useWebSocket`:** auto-reconnect exponential backoff (1s→30s max), heartbeat ping 25s, callback trong ref để tránh re-connect khi parent re-render.

**`VitalsChart`:** Chart.js multi-axis line chart, hiển thị HR + O2Sat + Temp + Resp cùng lúc (user cần thấy correlation). `spanGaps: true` để skip NaN.

**`RiskBadge`:**

- `< 0.3`: green "LOW"
- `0.3–0.7`: yellow "MEDIUM"
- `> 0.7`: red "HIGH" + `animate-pulse`

**State:** React Context + useReducer cho alerts global. React Query cho server state (cache, refetch). Không cần Redux.

## Config (`.env`)

```
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws/predictions
```

## Design

- **Colors:** blue-600 primary, green/yellow/red cho risk levels
- **Layout:** `max-w-7xl mx-auto`, mobile-first grid
- **Typography:** `tabular-nums` cho số liệu
- **Animation:** subtle only - đây là tool y tế, không flashy

## TS types (sync với backend Pydantic)

```ts
type Patient = {
  id: string;
  age: number | null;
  gender: 0 | 1 | null;
  current_risk: number;
  last_updated: string;
};

type Vital = {
  hour: number;
  hr: number | null;
  o2sat: number | null;
  temp: number | null;
  // ...
};

type Prediction = {
  hour: number;
  sepsis_risk: number;
  model_version: string;
  predicted_at: string;
};
```

## Setup

```bash
cd frontend
npm install
cp .env.example .env
npm run dev    # http://localhost:5173
npm run build  # → dist/
```

## Test priorities

- `useWebSocket`: connect, message, reconnect
- `RiskBadge`: render đúng color theo risk
- `VitalsChart`: render với data có NaN
- `Dashboard`: stats tính đúng

## Common issues

- **CORS error:** backend phải set `FRONTEND_ORIGIN` đúng
- **Chart không update:** đảm bảo data là **new reference** (React Query handle tự động)
- **Build size lớn:** import từng Chart.js component, không `import *`
- **WebSocket disconnect:** check backend ws_ping config

## DO NOT

- ❌ Redux/MobX (overkill)
- ❌ Inline style → dùng Tailwind
- ❌ Fetch trong component → dùng React Query hook
- ❌ Hardcode API URL → `import.meta.env.VITE_API_URL`
- ❌ Skip TypeScript types
