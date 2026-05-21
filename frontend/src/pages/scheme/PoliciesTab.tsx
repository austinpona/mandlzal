import { useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { Policy, SchemeType } from "../../types";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate, formatMoney } from "../../utils";


export function PoliciesTab() {
  const { scheme } = useOutletContext<{ scheme: SchemeType }>();
  const q = useQuery({
    queryKey: ["scheme-policies", scheme],
    queryFn: () => api.get<Policy[]>(`/policies?scheme_type=${scheme}`),
  });

  if (q.isLoading) return <div className="text-slate-500">Loading…</div>;
  if (q.error) return <div className="text-red-600">Failed to load policies.</div>;
  const rows = q.data!;
  if (rows.length === 0) {
    return <div className="card p-6 text-slate-500">No policies yet.</div>;
  }

  return (
    <div className="card divide-y">
      {rows.map((p) => (
        <div key={p.id} className="flex items-center justify-between p-4">
          <div>
            <div className="font-medium text-slate-800">Policy #{p.id}</div>
            <div className="text-xs text-slate-500">
              Customer {p.customer_id} · started {formatDate(p.start_date)}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-sm text-slate-700">
              {formatMoney(p.premium_amount)} / mo
            </div>
            <StatusBadge status={p.status} />
          </div>
        </div>
      ))}
    </div>
  );
}
