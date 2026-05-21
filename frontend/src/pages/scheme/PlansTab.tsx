import { useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { SchemeType } from "../../types";
import { formatMoney } from "../../utils";


interface CoverPlan {
  id: number;
  category: string;
  cover_type: string;
  scheme_type: SchemeType;
  monthly_premium: string;
  max_dependents: number;
  description: string | null;
  is_active: boolean;
}


export function PlansTab() {
  const { scheme } = useOutletContext<{ scheme: SchemeType }>();
  const q = useQuery({
    queryKey: ["scheme-plans", scheme],
    queryFn: () => api.get<CoverPlan[]>(`/cover-plans?scheme_type=${scheme}`),
  });

  if (q.isLoading) return <div className="text-slate-500">Loading…</div>;
  if (q.error) return <div className="text-red-600">Failed to load plans.</div>;
  const rows = q.data!;
  if (rows.length === 0) {
    return <div className="card p-6 text-slate-500">No plans configured for this scheme yet.</div>;
  }

  return (
    <div className="card divide-y">
      {rows.map((p) => (
        <div key={p.id} className="p-4">
          <div className="flex items-center justify-between">
            <div className="font-medium text-slate-800">{p.cover_type}</div>
            <div className="text-sm text-slate-700">{formatMoney(p.monthly_premium)} / mo</div>
          </div>
          <div className="text-xs text-slate-500 mt-1">
            {p.description}
            {p.max_dependents > 0 && ` · up to ${p.max_dependents} dependents`}
          </div>
        </div>
      ))}
    </div>
  );
}
