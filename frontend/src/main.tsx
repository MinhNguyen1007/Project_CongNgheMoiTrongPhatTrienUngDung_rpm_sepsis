import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import "./index.css";
import { AlertsProvider } from "@/context/AlertsContext";
import { WebSocketProvider } from "@/context/WebSocketContext";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

// Provider order: Query (state) → Alerts (cache) → WebSocket (đẩy event vào
// cả 2 layer trên). Router cuối cùng để dùng useNavigate trong WS handler.
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <AlertsProvider>
        <WebSocketProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </WebSocketProvider>
      </AlertsProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
