import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Plus, Search } from "lucide-react";
import { useState, useMemo } from "react";
import { api } from "../api/client";
import type { Customer } from "../types";
import { StatusBadge } from "../components/StatusBadge";
import { useAuth } from "../auth/AuthContext";

export function CustomersPage() {
  const { canWrite } = useAuth();
  const [q, setQ] = useState("");
  const { data, isLoading, error } = useQuery({
    queryKey: ["customers"],
    queryFn: () => api.get<Customer[]>("/customers"),
  });

  const filtered = useMemo(() => {
    if (!data) return [];
    const needle = q.trim().toLowerCase();
    if (!needle) return data;
    return data.filter((c) =>
      c.full_name.toLowerCase().includes(needle) ||
      c.id_number.toLowerCase().includes(needle) ||
      (c.email || "").toLowerCase().includes(needle),
    );
  }, [data, q]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Customers</h1>
          <p className="text-sm text-slate-500">All policy holders.</p>
        </div>
        {canWrite && (
          <Link to="/customers/new" className="btn-primary"><Plus size={16} /> New customer</Link>
        )}
      </div>

      <div className="card p-3 flex items-center gap-2">
        <Search size={16} className="text-slate-400 ml-2" />
        <input
          className="flex-1 px-2 py-1.5 text-sm outline-none"
          placeholder="Search by name, ID number or email…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="table-th">Name</th>
              <th className="table-th">ID number</th>
              <th className="table-th">Phone</th>
              <th className="table-th">Email</th>
              <th className="table-th">Status</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td className="table-td" colSpan={5}>Loading…</td></tr>
            )}
            {error && (
              <tr><td className="table-td text-red-600" colSpan={5}>Failed to load customers.</td></tr>
            )}
            {filtered.map((c) => (
              <tr key={c.id} className="hover:bg-slate-50">
                <td className="table-td font-medium">
                  <Link to={`/customers/${c.id}`} className="text-brand-700 hover:underline">{c.full_name}</Link>
                </td>
                <td className="table-td">{c.id_number}</td>
                <td className="table-td">{c.phone || "—"}</td>
                <td className="table-td">{c.email || "—"}</td>
                <td className="table-td"><StatusBadge status={c.status} /></td>
              </tr>
            ))}
            {!isLoading && filtered.length === 0 && (
              <tr><td className="table-td text-slate-500" colSpan={5}>No customers found.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
