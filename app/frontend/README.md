# Frontend — Sepsis Monitoring Dashboard

> 5 màn real-time + RBAC cho hệ thống giám sát ICU. Stack: React 19 + Vite 8 + TypeScript 6 strict + TailwindCSS 4 + Zustand + TanStack Query + React Router 6 + Recharts.

Đồng nghiệp mới: đọc [README root](../../README.md) trước để setup cả hệ thống, rồi quay lại đây.

## Dev

```bash
npm ci                  # lần đầu
npm run dev             # :5173, hot reload, proxy /api → backend :8000
npm run build           # tsc -b && vite build → dist/
npm run lint            # ESLint + TypeScript strict
```

## Cấu trúc

```
src/
├── api/client.ts        # fetch + bearer token injection + auto-logout 401
├── hooks/useAlertStream.ts  # WebSocket /ws/alerts auto-reconnect 2s
├── stores/
│   ├── authStore.ts     # Zustand + localStorage persist (rpm_auth key)
│   └── patientsStore.ts # Zustand (WS secondary; server polling primary)
├── routes/
│   ├── Login.tsx        # dark glassmorphism, gradient submit
│   ├── PatientList.tsx  # TanStack Query polling 5s, ALARM pulse
│   ├── PatientDetail.tsx # 3 chart: proba timeline, vitals, temp (tách scale 35-41°C)
│   ├── AlertsFeed.tsx   # dual-tab Live (WS) + History (DB + acknowledge)
│   └── AdminSettings.tsx # CRUD users (admin-only, RoleGate guard)
├── components/
│   ├── AppLayout.tsx    # nav + user badge + logout
│   ├── ProtectedRoute.tsx # redirect /login nếu !isAuthenticated
│   └── RoleGate.tsx     # ẩn UI theo role
└── types/api.ts         # mirror backend schemas
```

## Pitfalls đã gặp (đọc trước khi code để tránh)

- **Zustand selector trả collection** — KHÔNG viết `s => Object.values(s.patients)` (tạo array mới mỗi render → infinite loop → màn hình trắng). Subscribe ref stable `s => s.patients`, `Object.values(...)` ngoài (quyết định #26 CLAUDE.md).
- **Tailwind 4** dùng `@tailwindcss/vite` plugin, KHÔNG có `tailwind.config.js` hay PostCSS. Chỉ `@import "tailwindcss";` trong `index.css` (quyết định #25).
- **TypeScript tsconfig** dùng JSONC (có comment + trailing comma) → pre-commit `check-json` đã exclude 2 file này.

## API proxy dev

`vite.config.ts` đã set proxy:

- `/api/*` → `http://localhost:8000/*`
- `/ws/*` → `ws://localhost:8000/ws/*`

Khi chạy `npm run dev`, frontend gọi `/api/predict` sẽ tự proxy sang backend — không cần CORS config.

## Default login

Seed tự động khi backend khởi động lần đầu:

- Username: `admin`
- Password: `admin123`
- Role: `admin` (thấy được mọi thứ, có `/admin` route)

Tạo user role khác qua UI `/admin` hoặc API `POST /auth/register`.
