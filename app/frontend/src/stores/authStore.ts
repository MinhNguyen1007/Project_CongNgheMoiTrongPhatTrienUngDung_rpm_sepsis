import { create } from "zustand";

interface AuthState {
  token: string | null;
  username: string | null;
  role: string | null;
  isAuthenticated: boolean;
  login: (token: string, username: string, role: string) => void;
  logout: () => void;
}

const STORAGE_KEY = "rpm_auth";

function loadPersistedAuth(): Pick<AuthState, "token" | "username" | "role"> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return {
        token: parsed.token ?? null,
        username: parsed.username ?? null,
        role: parsed.role ?? null,
      };
    }
  } catch {
    // ignore
  }
  return { token: null, username: null, role: null };
}

const persisted = loadPersistedAuth();

export const useAuthStore = create<AuthState>((set) => ({
  token: persisted.token,
  username: persisted.username,
  role: persisted.role,
  isAuthenticated: persisted.token !== null,

  login: (token, username, role) => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ token, username, role }),
    );
    set({ token, username, role, isAuthenticated: true });
  },

  logout: () => {
    localStorage.removeItem(STORAGE_KEY);
    set({ token: null, username: null, role: null, isAuthenticated: false });
  },
}));
