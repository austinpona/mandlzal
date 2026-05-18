import type { FieldPendingSubmission, FieldDevice, FieldSignupDraft } from "./types";

const DEVICE_KEY = "mandlzi.field.device";
const DRAFT_KEY = "mandlzi.field.draft";
const QUEUE_KEY = "mandlzi.field.queue";

function readJSON<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeJSON(key: string, value: unknown) {
  localStorage.setItem(key, JSON.stringify(value));
}

export function getFieldDevice(): FieldDevice | null {
  return readJSON<FieldDevice | null>(DEVICE_KEY, null);
}

export function saveFieldDevice(device: FieldDevice) {
  writeJSON(DEVICE_KEY, device);
}

export function clearFieldDevice() {
  localStorage.removeItem(DEVICE_KEY);
}

export function getDraft(): FieldSignupDraft | null {
  return readJSON<FieldSignupDraft | null>(DRAFT_KEY, null);
}

export function saveDraft(draft: FieldSignupDraft) {
  writeJSON(DRAFT_KEY, draft);
}

export function clearDraft() {
  localStorage.removeItem(DRAFT_KEY);
}

export function listQueue(): FieldPendingSubmission[] {
  return readJSON<FieldPendingSubmission[]>(QUEUE_KEY, []);
}

export function saveQueue(rows: FieldPendingSubmission[]) {
  writeJSON(QUEUE_KEY, rows);
}

export function upsertQueue(row: FieldPendingSubmission) {
  const rows = listQueue();
  const idx = rows.findIndex((r) => r.client_uuid === row.client_uuid);
  if (idx >= 0) rows[idx] = row;
  else rows.unshift(row);
  saveQueue(rows);
}

export function clearFieldData() {
  clearDraft();
  clearFieldDevice();
  localStorage.removeItem(QUEUE_KEY);
}

export function newClientUuid() {
  if ("randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function dataUrlToFile(dataUrl: string, fileName: string): File {
  const [meta, data] = dataUrl.split(",");
  const mime = meta.match(/data:(.*?);/)?.[1] || "image/jpeg";
  const bytes = atob(data);
  const buffer = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i += 1) buffer[i] = bytes.charCodeAt(i);
  return new File([buffer], fileName, { type: mime });
}

