import { useQuery } from "@tanstack/react-query";
import { Users, FileCheck, AlertTriangle, TrendingUp, Wallet, Bell } from "lucide-react";
import { api } from "../api/client";
import type { DashboardSummary, NotificationItem } from "../types";
import { formatMoney, formatDate } from "../utils";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

function StatCard({ icon, label, value, sub, tone = "default" }: {
  icon: React.ReactNode; label: string; value: string | number;
  sub?: string; tone?: "default" | "good" | "warn" | "bad";
}) {
  const tones = {
    default: "bg-white",
    good: "bg-emerald-50 border-emerald-200",
    warn: "bg-amber-50 border-amber-200",
    bad: "bg-red-50 border-red-200",
  } as const;
  return (
    <div className={`card p-5 ${tones[tone]}`}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</span>
        <span className="text-slate-400">{icon}</span>
      </div>
      <div className="mt-2 text-2xl font-bold text-slate-900">{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </div>
  );
}

export function DashboardPage() {
  const { canWrite } = useAuth();
  const summary = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<DashboardSummary>("/dashboard"),
  });

  const notes = useQuery({
    queryKey: ["notifications", "recent"],
    queryFn: () => api.get<NotificationItem[]>("/notifications"),
  });

  if (summary.isLoading) return <div className="text-slate-500">Loading dashboard…</div>;
  if (summary.error) return <div className="text-red-600">Failed to load dashboard.</div>;
  const s = summary.data!;
  const collected = parseFloat(s.revenue_this_month);
  const expected = parseFloat(s.expected_revenue_this_month);
  const pct = expected > 0 ? Math.min(100, Math.round((collected / expected) * 100)) : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-sm text-slate-500">Operational snapshot for the current month.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={<Users size={18} />} label="Customers" value={s.total_customers}
                  sub={`${s.active_customers} active · ${s.lapsed_customers} lapsed`} />
        <StatCard icon={<FileCheck size={18} />} label="Policies" value={s.total_policies}
                  sub={`${s.active_policies} active · ${s.lapsed_policies} lapsed`} />
        <StatCard icon={<TrendingUp size={18} />} label="Paid this month" value={s.paid_this_month} tone="good" />
        <StatCard icon={<AlertTriangle size={18} />} label="Overdue this month" value={s.overdue_this_month}
                  tone={s.overdue_this_month > 0 ? "bad" : "default"} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="card p-5 lg:col-span-2">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold flex items-center gap-2"><Wallet size={16} /> Revenue this month</h2>
            {canWrite && <Link to="/payments/new" className="btn-secondary">Record payment</Link>}
          </div>
          <div className="flex items-end gap-4">
            <div>
              <div className="text-3xl font-bold">{formatMoney(collected)}</div>
              <div className="text-xs text-slate-500">collected of {formatMoney(expected)} expected</div>
            </div>
            <div className="text-sm font-semibold text-slate-700">{pct}%</div>
          </div>
          <div className="mt-3 h-2 w-full bg-slate-100 rounded-full overflow-hidden">
            <div className="h-full bg-brand-600" style={{ width: `${pct}%` }} />
          </div>
          <div className="mt-4 grid grid-cols-3 gap-3 text-center text-xs">
            <div className="rounded bg-emerald-50 p-2"><div className="font-semibold text-emerald-700">{s.paid_this_month}</div><div className="text-slate-500">Paid</div></div>
            <div className="rounded bg-amber-50 p-2"><div className="font-semibold text-amber-700">{s.unpaid_this_month}</div><div className="text-slate-500">Not paid</div></div>
            <div className="rounded bg-red-50 p-2"><div className="font-semibold text-red-700">{s.overdue_this_month}</div><div className="text-slate-500">Overdue</div></div>
          </div>
        </div>

        <div className="card p-5">
          <h2 className="font-semibold flex items-center gap-2 mb-3"><Bell size={16} /> Recent notifications</h2>
          {notes.isLoading && <div className="text-sm text-slate-500">Loading…</div>}
          {notes.data && notes.data.length === 0 && (
            <div className="text-sm text-slate-500">No notifications yet.</div>
          )}
          <ul className="space-y-3 max-h-72 overflow-y-auto">
            {notes.data?.slice(0, 8).map((n) => (
              <li key={n.id} className="text-sm border-b border-slate-100 pb-2 last:border-0">
                <div className="font-medium text-slate-800">{n.type.replace(/_/g, " ")}</div>
                <div className="text-slate-600">{n.message}</div>
                <div className="text-[11px] text-slate-400 mt-0.5">{formatDate(n.created_at)}</div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
