import { Link, NavLink, Outlet } from "react-router-dom";
import { LayoutDashboard, Users, Bell, FileText, Wallet, Smartphone } from "lucide-react";
import { useAuth } from "../auth/AuthContext";

const ROLE_BADGE: Record<string, string> = {
  admin: "text-rose-300",
  agent: "text-amber-300",
  viewer: "text-slate-400",
};

export function Layout() {
  const { user, canAdmin } = useAuth();

  const linkCls = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition ${
      isActive ? "bg-brand-600 text-white" : "text-slate-300 hover:bg-slate-800 hover:text-white"
    }`;

  return (
    <div className="min-h-full flex">
      <aside className="w-60 shrink-0 bg-slate-900 text-white flex flex-col">
        <div className="px-5 py-5 border-b border-slate-800">
          <Link to="/" className="text-lg font-bold tracking-tight">
            Mandlzi <span className="text-brand-500">·</span>
          </Link>
          <p className="text-xs text-slate-400 mt-1">Subscription Management</p>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1">
          <NavLink to="/" end className={linkCls}>
            <LayoutDashboard size={18} /> Dashboard
          </NavLink>
          <NavLink to="/customers" className={linkCls}>
            <Users size={18} /> Customers
          </NavLink>
          <NavLink to="/payments/new" className={linkCls}>
            <Wallet size={18} /> Record payment
          </NavLink>
          <NavLink to="/notifications" className={linkCls}>
            <Bell size={18} /> Notifications
          </NavLink>
          <NavLink to="/audit" className={linkCls}>
            <FileText size={18} /> Audit log
          </NavLink>
          {canAdmin && (
            <NavLink to="/devices" className={linkCls}>
              <Smartphone size={18} /> Field devices
            </NavLink>
          )}
        </nav>
        <div className="border-t border-slate-800 p-3">
          <div className="text-xs text-slate-400 mb-2 px-2">
            {user?.full_name || user?.email}
            {user?.role && (
              <span className={`ml-2 ${ROLE_BADGE[user.role] ?? "text-slate-400"}`}>
                {user.role}
              </span>
            )}
          </div>
          <div className="px-2 text-xs text-slate-500">Login removed for demo access.</div>
        </div>
      </aside>
      <main className="flex-1 overflow-x-hidden">
        <div className="max-w-7xl mx-auto p-6 lg:p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
