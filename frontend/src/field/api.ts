import { clearFieldData, dataUrlToFile, getFieldDevice, listQueue, saveQueue } from "./storage";
import type {
  FieldCoverPlan,
  FieldDevice,
  FieldPendingSubmission,
  FieldSubmissionPayload,
  FieldSubmissionResponse,
} from "./types";

const BASE = "/api/api/field";

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

export async function enrollFieldDevice(code: string, name: string): Promise<FieldDevice> {
  const res = await request<{ device_id: number; name: string; device_jwt: string }>("/enroll", {
    method: "POST",
    body: JSON.stringify({ code, name }),
  }, "");
  return { device_id: res.device_id, name: res.name, jwt: res.device_jwt, enrolled_at: new Date().toISOString() };
}

export async function fetchFieldPlans(): Promise<FieldCoverPlan[]> {
  const res = await request<{ plans: FieldCoverPlan[] }>("/cover-plans");
  return res.plans;
}

export async function uploadFieldPhoto(dataUrl: string): Promise<{ id_photo_id: string; path: string }> {
  const form = new FormData();
  form.append("file", dataUrlToFile(dataUrl, "id-photo.jpg"));
  return request("/photos", { method: "POST", body: form });
}

export async function postFieldSubmission(payload: FieldSubmissionPayload): Promise<FieldSubmissionResponse> {
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
