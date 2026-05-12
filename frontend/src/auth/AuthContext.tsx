import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, getToken, setToken } from "../api/client";
import type { User } from "../types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(!!getToken());

  // On mount, if we have a token, fetch the user.
  useEffect(() => {
    let cancelled = false;
    if (!getToken()) { setLoading(false); return; }
    api.get<User>("/auth/me")
      .then((u) => { if (!cancelled) setUser(u); })
      .catch(() => { setToken(null); })
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
    setUser(null);
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
