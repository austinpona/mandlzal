import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { AuditLogItem } from "../types";
import { formatDate } from "../utils";

export function AuditPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["audit"],
    queryFn: () => api.get<AuditLogItem[]>("/audit-logs"),
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Audit log</h1>
        <p className="text-sm text-slate-500">Most recent 100 mutating actions.</p>
      </div>
      <div className="card overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="table-th">When</th>
              <th className="table-th">Actor</th>
              <th className="table-th">Action</th>
              <th className="table-th">Entity</th>
              <th className="table-th">Details</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && <tr><td className="table-td" colSpan={5}>Loading…</td></tr>}
            {error && <tr><td className="table-td text-red-600" colSpan={5}>Failed to load.</td></tr>}
            {data?.length === 0 && <tr><td className="table-td text-slate-500" colSpan={5}>No events yet.</td></tr>}
            {data?.map((l) => (
              <tr key={l.id} className="align-top">
                <td className="table-td whitespace-nowrap">{formatDate(l.created_at)}</td>
                <td className="table-td">{l.actor || "system"}</td>
                <td className="table-td font-medium">{l.action}</td>
                <td className="table-td">{l.entity_type}#{l.entity_id ?? "—"}</td>
                <td className="table-td">
                  <pre className="text-[11px] text-slate-600 whitespace-pre-wrap break-all max-w-md">{l.details || ""}</pre>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
