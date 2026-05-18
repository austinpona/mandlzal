import { clearFieldData, dataUrlToFile, getFieldDevice, listQueue, saveQueue } from "./storage";
import type {
  FieldCoverPlan,
  FieldDevice,
  FieldPendingSubmission,
  FieldSubmissionPayload,
  FieldSubmissionResponse,
} from "./types";

const BASE = "/api/api/field";

const DEMO_PLANS: FieldCoverPlan[] = [
  {
    id: 101,
    category: "me",
    cover_type: "Me",
    monthly_premium: "120.00",
    max_dependents: 0,
    description: "Covers the main member.",
  },
  {
    id: 102,
    category: "me_and_family",
    cover_type: "Me and My Family",
    monthly_premium: "360.00",
    max_dependents: 4,
    description: "Covers the main member and up to 4 dependents.",
  },
  {
    id: 103,
    category: "extended_family",
    cover_type: "Extended Family",
    monthly_premium: "520.00",
    max_dependents: 8,
    description: "Covers a larger family group.",
  },
  {
    id: 104,
    category: "livestock_benefits",
    cover_type: "Cattle in December",
    monthly_premium: "200.00",
    max_dependents: 0,
    description: "Livestock benefit plan with no beneficiaries.",
  },
];

export class FieldApiError extends Error {
  status: number;
  body: any;
  constructor(status: number, body: any) {
    const detail = body?.detail;
    super(typeof detail === "string" ? detail : JSON.stringify(detail || body || `HTTP ${status}`));
    this.status = status;
    this.body = body;
  }
}

async function request<T>(path: string, opts: RequestInit = {}, jwt?: string): Promise<T> {
  const headers = new Headers(opts.headers);
  if (!headers.has("Content-Type") && opts.body && !(opts.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const token = jwt ?? getFieldDevice()?.jwt;
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${BASE}${path}`, { ...opts, headers });
  const text = await res.text();
  const parsed = text ? safeJSON(text) : null;
  if (!res.ok) {
    if (res.status === 401 && parsed?.detail?.code === "DEVICE_REVOKED") clearFieldData();
    throw new FieldApiError(res.status, parsed);
  }
  return parsed as T;
}

function safeJSON(text: string) {
  try { return JSON.parse(text); } catch { return text; }
}

function isDemo() {
  return import.meta.env.VITE_DEMO === "true";
}

function demoDelay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), 250));
}

export async function enrollFieldDevice(code: string, name: string): Promise<FieldDevice> {
  if (isDemo()) {
    if (!code.trim() || !name.trim()) {
      throw new FieldApiError(400, { detail: "Enter a code and phone name" });
    }
    return demoDelay({
      device_id: 9001,
      name: name.trim(),
      jwt: "demo-field-device-token",
      enrolled_at: new Date().toISOString(),
    });
  }
  const res = await request<{ device_id: number; name: string; device_jwt: string }>("/enroll", {
    method: "POST",
    body: JSON.stringify({ code, name }),
  }, "");
  return { device_id: res.device_id, name: res.name, jwt: res.device_jwt, enrolled_at: new Date().toISOString() };
}

export async function fetchFieldPlans(): Promise<FieldCoverPlan[]> {
  if (isDemo()) return demoDelay(DEMO_PLANS);
  const res = await request<{ plans: FieldCoverPlan[] }>("/cover-plans");
  return res.plans;
}

export async function uploadFieldPhoto(dataUrl: string): Promise<{ id_photo_id: string; path: string }> {
  if (isDemo()) {
    const path = `id_photos/demo-${Date.now()}.jpg`;
    return demoDelay({ id_photo_id: path, path });
  }
  const form = new FormData();
  form.append("file", dataUrlToFile(dataUrl, "id-photo.jpg"));
  return request("/photos", { method: "POST", body: form });
}

export async function postFieldSubmission(payload: FieldSubmissionPayload): Promise<FieldSubmissionResponse> {
  if (isDemo()) {
    const base = Math.floor(Date.now() / 1000);
    return demoDelay({
      field_submission_id: base,
      results: payload.signups.map((signup, index) => ({
        local_id: signup.local_id,
        status: "ok",
        customer_id: base + index + 1,
        policy_id: base + index + 101,
        payment_id: signup.first_payment ? base + index + 201 : null,
      })),
    });
  }
  return request("/submissions", { method: "POST", body: JSON.stringify(payload) });
}

export async function drainFieldQueue(): Promise<FieldPendingSubmission[]> {
  if (!navigator.onLine) return listQueue();
  const rows = listQueue();
  const next: FieldPendingSubmission[] = [];
  for (const row of rows) {
    if (row.status === "synced") {
      next.push(row);
      continue;
    }
    let working: FieldPendingSubmission = {
      ...row,
      status: "syncing",
      attempts: row.attempts + 1,
      updated_at: new Date().toISOString(),
      last_error: undefined,
    };
    try {
      if (working.photo_data_url && !working.payload.signups[0]?.id_photo_id) {
        const photo = await uploadFieldPhoto(working.photo_data_url);
        working = {
          ...working,
          payload: {
            ...working.payload,
            signups: working.payload.signups.map((s, i) => i === 0 ? { ...s, id_photo_id: photo.id_photo_id } : s),
          },
          photo_data_url: undefined,
        };
      }
      const result = await postFieldSubmission(working.payload);
      next.push({ ...working, status: "synced", server_result: result, updated_at: new Date().toISOString() });
    } catch (err) {
      next.push({
        ...working,
        status: "failed",
        last_error: err instanceof Error ? err.message : "Sync failed",
        updated_at: new Date().toISOString(),
      });
    }
    saveQueue(next.concat(rows.slice(rows.indexOf(row) + 1)));
  }
  saveQueue(next);
  return next;
}
