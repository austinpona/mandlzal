import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, getToken, setToken } from "../api/client";
import type { User } from "../types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => void;
  canWrite: boolean;
  canAdmin: boolean;
}

const AuthContext = createContext<AuthState | null>(null);

const publicAdmin: User = {
  id: 0,
  email: "open-access@mandlzi.local",
  full_name: "Open Access",
  is_admin: true,
  role: "admin",
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(publicAdmin);
  const [loading, setLoading] = useState<boolean>(!!getToken());

  // On mount, honor an existing token; otherwise run the UI in open-access mode.
  useEffect(() => {
    let cancelled = false;
    if (!getToken()) {
      setUser(publicAdmin);
      setLoading(false);
      return;
    }
    api.get<User>("/auth/me")
      .then((u) => { if (!cancelled) setUser(u); })
      .catch(() => {
        setToken(null);
        if (!cancelled) setUser(publicAdmin);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  async function login(email: string, password: string) {
    const res = await api.postForm<{ access_token: string }>(
      "/auth/login", { username: email, password },
    );
    setToken(res.access_token);
    const me = await api.get<User>("/auth/me");
    setUser(me);
  }

  async function register(email: string, password: string, fullName?: string) {
    await api.post<User>("/auth/register", { email, password, full_name: fullName });
    await login(email, password);
  }

  function logout() {
    setToken(null);
    setUser(publicAdmin);
  }

  const canAdmin = user?.role === "admin";
  const canWrite = canAdmin || user?.role === "agent";

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, canWrite, canAdmin }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
