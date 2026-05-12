import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { NotificationItem } from "../types";
import { formatDate } from "../utils";

export function NotificationsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.get<NotificationItem[]>("/notifications"),
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Notifications</h1>
        <p className="text-sm text-slate-500">System-generated alerts.</p>
      </div>
      <div className="card overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="table-th">When</th>
              <th className="table-th">Type</th>
              <th className="table-th">Customer</th>
              <th className="table-th">Policy</th>
              <th className="table-th">Message</th>
              <th className="table-th">Delivery</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && <tr><td className="table-td" colSpan={6}>Loading…</td></tr>}
            {error && <tr><td className="table-td text-red-600" colSpan={6}>Failed to load.</td></tr>}
            {data?.length === 0 && <tr><td className="table-td text-slate-500" colSpan={6}>No notifications.</td></tr>}
            {data?.map((n) => (
              <tr key={n.id}>
                <td className="table-td">{formatDate(n.created_at)}</td>
                <td className="table-td font-medium">{n.type.replace(/_/g, " ")}</td>
                <td className="table-td">#{n.customer_id}</td>
                <td className="table-td">{n.policy_id ? `#${n.policy_id}` : "—"}</td>
                <td className="table-td">{n.message}</td>
                <td className="table-td">
                  {n.is_sent ? (
                    <span className="text-emerald-600">✅ {n.sent_at ? formatDate(n.sent_at) : ""}</span>
                  ) : n.last_error ? (
                    <span className="text-red-600" title={n.last_error}>
                      ⚠ retry {n.delivery_attempts}
                    </span>
                  ) : (
                    <span className="text-slate-500">pending</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
