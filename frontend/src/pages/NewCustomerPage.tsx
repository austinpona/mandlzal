import { useState, FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import type { Customer } from "../types";

export function NewCustomerPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [form, setForm] = useState({ full_name: "", id_number: "", phone: "", email: "" });
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => api.post<Customer>("/customers", {
      full_name: form.full_name,
      id_number: form.id_number,
      phone: form.phone || null,
      email: form.email || null,
    }),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ["customers"] });
      navigate(`/customers/${c.id}`);
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Failed to create"),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    mutation.mutate();
  }

  function update<K extends keyof typeof form>(k: K, v: string) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  return (
    <div className="max-w-2xl space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">New customer</h1>
        <p className="text-sm text-slate-500">Capture a new policy holder.</p>
      </div>
      <form onSubmit={submit} className="card p-6 space-y-4">
        <div>
          <label className="label" htmlFor="cust-full-name">Full name *</label>
          <input id="cust-full-name" className="input" required value={form.full_name} onChange={(e) => update("full_name", e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="cust-id-number">ID number *</label>
          <input id="cust-id-number" className="input" required value={form.id_number} onChange={(e) => update("id_number", e.target.value)} />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="label" htmlFor="cust-phone">Phone</label>
            <input id="cust-phone" className="input" value={form.phone} onChange={(e) => update("phone", e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="cust-email">Email</label>
            <input id="cust-email" className="input" type="email" value={form.email} onChange={(e) => update("email", e.target.value)} />
          </div>
        </div>
        {error && <div className="text-sm text-red-600 bg-red-50 border border-red-200 px-3 py-2 rounded">{error}</div>}
        <div className="flex gap-2 justify-end">
          <button type="button" className="btn-secondary" onClick={() => navigate(-1)}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={mutation.isPending}>
            {mutation.isPending ? "Saving…" : "Create customer"}
          </button>
        </div>
      </form>
    </div>
  );
}
