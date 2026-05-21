import { useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { SchemeOverviewResponse, SchemeType } from "../../types";
import { formatMoney } from "../../utils";


function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card p-5">
      <div className="text-xs uppercase text-slate-500 font-semibold mb-2">{title}</div>
      {children}
    </div>
  );
}


export function OverviewTab() {
  const { scheme } = useOutletContext<{ scheme: SchemeType }>();
  const q = useQuery({
    queryKey: ["scheme-overview", scheme],
    queryFn: () => api.get<SchemeOverviewResponse>(`/schemes/${scheme}/overview`),
  });

  if (q.isLoading) return <div className="text-slate-500">Loading…</div>;
  if (q.error) return <div className="text-red-600">Failed to load overview.</div>;
  const d = q.data!;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title="Customers">
          <div className="text-3xl font-semibold">{d.active_customers}</div>
          <div className="text-xs text-slate-500 mt-1">{d.lapsed_customers} lapsed</div>
        </Card>
        <Card title="Policies">
          <div className="text-3xl font-semibold">{d.active_policies}</div>
          <div className="text-xs text-slate-500 mt-1">{d.lapsed_policies} lapsed</div>
        </Card>
        <Card title="This month">
          <div className="flex gap-3 text-sm">
            <span className="text-emerald-600">{d.paid_this_month} paid</span>
            <span className="text-amber-600">{d.unpaid_this_month} unpaid</span>
            <span className="text-rose-600">{d.overdue_this_month} overdue</span>
          </div>
        </Card>
        <Card title="Revenue this month">
          <div className="text-2xl font-semibold">{formatMoney(d.revenue_this_month)}</div>
          <div className="text-xs text-slate-500 mt-1">
            of {formatMoney(d.expected_revenue_this_month)} expected
          </div>
        </Card>
      </div>
      <div className="card p-4 text-sm text-slate-600">
        {d.plan_count === 0
          ? "0 plans configured — add one to begin."
          : `${d.plan_count} plan${d.plan_count === 1 ? "" : "s"} in this scheme.`}
      </div>
    </div>
  );
}
