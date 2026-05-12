import { ReactNode } from "react";

const palette: Record<string, string> = {
  PAID: "bg-emerald-100 text-emerald-700 ring-emerald-200",
  NOT_PAID: "bg-amber-100 text-amber-700 ring-amber-200",
  OVERDUE: "bg-red-100 text-red-700 ring-red-200",
  PARTIAL: "bg-blue-100 text-blue-700 ring-blue-200",
  active: "bg-emerald-100 text-emerald-700 ring-emerald-200",
  lapsed: "bg-red-100 text-red-700 ring-red-200",
  cancelled: "bg-slate-200 text-slate-700 ring-slate-300",
  paid: "bg-emerald-100 text-emerald-700 ring-emerald-200",
  pending: "bg-amber-100 text-amber-700 ring-amber-200",
  failed: "bg-red-100 text-red-700 ring-red-200",
};

export function StatusBadge({ status, children }: { status: string; children?: ReactNode }) {
  const cls = palette[status] ?? "bg-slate-100 text-slate-700 ring-slate-200";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 text-xs font-semibold rounded-full ring-1 ring-inset ${cls}`}>
      {children ?? status.replace(/_/g, " ")}
    </span>
  );
}
