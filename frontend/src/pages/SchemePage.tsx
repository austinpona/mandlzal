import { useParams, Navigate, NavLink, Outlet } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";

import { SCHEME_MANIFEST, SchemeType } from "../types";
import { ComingSoonScheme } from "./scheme/ComingSoonScheme";


const SUB_TABS: { to: string; label: string }[] = [
  { to: "",          label: "Overview" },
  { to: "customers", label: "Customers" },
  { to: "policies",  label: "Policies" },
  { to: "plans",     label: "Plans" },
];


export function SchemePage() {
  const { schemeType } = useParams<{ schemeType: string }>();
  const entry = SCHEME_MANIFEST.find((s) => s.type === schemeType);

  if (!entry) {
    return <Navigate to="/" replace />;
  }
  if (entry.status === "coming_soon") {
    return <ComingSoonScheme label={entry.label} />;
  }

  const scheme = entry.type as SchemeType;
  const tabCls = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-2 text-sm font-medium border-b-2 transition ${
      isActive
        ? "border-brand-600 text-brand-700"
        : "border-transparent text-slate-500 hover:text-slate-700"
    }`;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/" className="text-slate-500 hover:text-slate-700">
          <ArrowLeft size={18} />
        </Link>
        <h1 className="text-2xl font-bold tracking-tight">{entry.label}</h1>
      </div>
      <div className="border-b border-slate-200 flex gap-2">
        {SUB_TABS.map((t) => (
          <NavLink
            key={t.to || "overview"}
            to={t.to ? `/schemes/${scheme}/${t.to}` : `/schemes/${scheme}`}
            end={t.to === ""}
            className={tabCls}
          >
            {t.label}
          </NavLink>
        ))}
      </div>
      <Outlet context={{ scheme }} />
    </div>
  );
}
