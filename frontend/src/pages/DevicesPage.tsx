import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, RefreshCcw, ShieldOff, Smartphone } from "lucide-react";
import { api, ApiError } from "../api/client";
import type { FieldDeviceAdmin, FieldEnrollmentCode } from "../types";

export function DevicesPage() {
  const qc = useQueryClient();
  const devices = useQuery({
    queryKey: ["field-devices"],
    queryFn: () => api.get<{ devices: FieldDeviceAdmin[] }>("/admin/field/devices"),
  });
  const createCode = useMutation({
    mutationFn: () => api.post<FieldEnrollmentCode>("/admin/field/enrollment-codes", {}),
  });
  const revoke = useMutation({
    mutationFn: (id: number) => api.post(`/admin/field/devices/${id}/revoke`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["field-devices"] }),
  });

  return (
    <div className="mx-auto max-w-5xl space-y-5 p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Field devices</h1>
          <p className="text-sm text-slate-500">Enroll phones and revoke access when needed. Dev preview does not require login.</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={() => devices.refetch()} disabled={devices.isFetching}>
            <RefreshCcw size={16} /> Refresh
          </button>
          <button className="btn-primary" onClick={() => createCode.mutate()} disabled={createCode.isPending}>
            <KeyRound size={16} /> New code
          </button>
        </div>
      </div>

      {createCode.data && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
          <div className="text-sm text-emerald-700">Enrollment code</div>
          <div className="mt-1 font-mono text-3xl font-bold tracking-widest text-emerald-950">{createCode.data.code}</div>
          <div className="mt-1 text-sm text-emerald-700">
            Expires {new Date(createCode.data.expires_at).toLocaleString()}
          </div>
        </div>
      )}

      {createCode.error && <ErrorBox error={createCode.error} />}
      {revoke.error && <ErrorBox error={revoke.error} />}

      <div className="card overflow-hidden">
        <table className="min-w-full">
          <thead>
            <tr>
              <th className="table-th">Device</th>
              <th className="table-th">Status</th>
              <th className="table-th">Last seen</th>
              <th className="table-th">Action</th>
            </tr>
          </thead>
          <tbody>
            {(devices.data?.devices ?? []).map((device) => (
              <tr key={device.id}>
                <td className="table-td">
                  <div className="flex items-center gap-2">
                    <Smartphone size={16} className="text-slate-400" />
                    <div>
                      <div className="font-medium text-slate-900">{device.name}</div>
                      <div className="text-xs text-slate-500">#{device.id} · enrolled {new Date(device.enrolled_at).toLocaleDateString()}</div>
                    </div>
                  </div>
                </td>
                <td className="table-td">
                  <span className={device.status === "active" ? "text-emerald-700" : "text-red-700"}>{device.status}</span>
                </td>
                <td className="table-td">{device.last_seen_at ? new Date(device.last_seen_at).toLocaleString() : "-"}</td>
                <td className="table-td">
                  <button
                    className="btn-danger"
                    disabled={device.status === "revoked" || revoke.isPending}
                    onClick={() => revoke.mutate(device.id)}
                  >
                    <ShieldOff size={15} /> Revoke
                  </button>
                </td>
              </tr>
            ))}
            {!devices.isLoading && (devices.data?.devices ?? []).length === 0 && (
              <tr><td className="table-td text-slate-500" colSpan={4}>No devices enrolled.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ErrorBox({ error }: { error: unknown }) {
  const message = error instanceof ApiError ? error.message : error instanceof Error ? error.message : "Request failed";
  return <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{message}</div>;
}
