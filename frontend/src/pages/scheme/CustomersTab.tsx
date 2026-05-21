import { Link, useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { Customer, SchemeType } from "../../types";
import { StatusBadge } from "../../components/StatusBadge";


export function CustomersTab() {
  const { scheme } = useOutletContext<{ scheme: SchemeType }>();
  const q = useQuery({
    queryKey: ["scheme-customers", scheme],
    queryFn: () => api.get<Customer[]>(`/customers?scheme_type=${scheme}`),
  });

  if (q.isLoading) return <div className="text-slate-500">Loading…</div>;
  if (q.error) return <div className="text-red-600">Failed to load customers.</div>;
  const rows = q.data!;
  if (rows.length === 0) {
    return <div className="card p-6 text-slate-500">No customers yet.</div>;
  }

  return (
    <div className="card divide-y">
      {rows.map((c) => (
        <Link
          key={c.id}
          to={`/customers/${c.id}`}
          className="flex items-center justify-between p-4 hover:bg-slate-50"
        >
          <div>
            <div className="font-medium text-slate-800">{c.full_name}</div>
            <div className="text-xs text-slate-500">{c.id_number}</div>
          </div>
          <StatusBadge status={c.status} />
        </Link>
      ))}
    </div>
  );
}
