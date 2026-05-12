import { useState, FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../api/client";

export function LoginPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("admin123");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password, fullName);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 bg-gradient-to-br from-slate-100 via-white to-brand-50">
      <div className="card w-full max-w-md p-8">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-md bg-brand-600 flex items-center justify-center text-white">
            <ShieldCheck size={20} />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight">Mandlzi</h1>
            <p className="text-xs text-slate-500">Subscription Management</p>
          </div>
        </div>
        <h2 className="text-lg font-semibold mb-4">
          {mode === "login" ? "Sign in to continue" : "Create your account"}
        </h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === "register" && (
            <div>
              <label className="label" htmlFor="login-full-name">Full name</label>
              <input id="login-full-name" className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} />
            </div>
          )}
          <div>
            <label className="label" htmlFor="login-email">Email</label>
            <input id="login-email" className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="login-password">Password</label>
            <input id="login-password" className="input" type="password" required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          {error && <div className="text-sm text-red-600 bg-red-50 border border-red-200 px-3 py-2 rounded">{error}</div>}
          <button type="submit" className="btn-primary w-full" disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>
        <div className="text-center mt-4 text-sm text-slate-500">
          {mode === "login" ? (
            <>No account? <button className="text-brand-600 hover:underline" onClick={() => setMode("register")}>Register</button></>
          ) : (
            <>Already have an account? <button className="text-brand-600 hover:underline" onClick={() => setMode("login")}>Sign in</button></>
          )}
        </div>
        <p className="text-[11px] text-slate-400 text-center mt-6">
          Tip: seed creates <code>admin@example.com / admin123</code>
        </p>
      </div>
    </div>
  );
}
