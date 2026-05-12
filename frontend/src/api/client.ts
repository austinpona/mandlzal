// Tiny typed wrapper around fetch that injects the bearer token and parses errors.
const BASE = "/api";
const TOKEN_KEY = "mandlzi.token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  body: any;
  constructor(status: number, body: any, message: string) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

type RequestInitX = RequestInit & { form?: Record<string, string>; json?: any };

async function request<T>(path: string, opts: RequestInitX = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers as any) };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let body: BodyInit | undefined = opts.body as BodyInit | undefined;
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.json);
  } else if (opts.form) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    body = new URLSearchParams(opts.form).toString();
  }

  const res = await fetch(`${BASE}${path}`, { ...opts, headers, body });
  const text = await res.text();
  const parsed = text ? safeJSON(text) : null;
  if (!res.ok) {
    const msg = parsed?.detail
      ? Array.isArray(parsed.detail)
        ? parsed.detail.map((d: any) => d.msg).join("; ")
        : String(parsed.detail)
      : `HTTP ${res.status}`;
    throw new ApiError(res.status, parsed, msg);
  }
  return parsed as T;
}

function safeJSON(t: string) { try { return JSON.parse(t); } catch { return t; } }

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, json?: any) => request<T>(path, { method: "POST", json }),
  postForm: <T>(path: string, form: Record<string, string>) =>
    request<T>(path, { method: "POST", form }),
  patch: <T>(path: string, json?: any) => request<T>(path, { method: "PATCH", json }),
  delete: <T = void>(path: string) => request<T>(path, { method: "DELETE" }),
};
