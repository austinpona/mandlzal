import { useState, useEffect, FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import type { Customer, Policy, Member, Payment } from "../types";

export function NewPaymentPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const qc = useQueryClient();

  const [customerId, setCustomerId] = useState<string>(params.get("customer_id") || "");
  const [policyId, setPolicyId] = useState<string>("");
  const [memberId, setMemberId] = useState<string>("");
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<"debit_order" | "cash" | "eft">("debit_order");
  const [statusVal, setStatusVal] = useState<"paid" | "pending" | "failed">("paid");
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [reference, setReference] = useState("");
  const [error, setError] = useState<string | null>(null);

  const customers = useQuery({ queryKey: ["customers"], queryFn: () => api.get<Customer[]>("/customers") });

  // Load policies for the selected customer via the customer's status endpoint
  // (cheap way to get all linked policy ids without a dedicated /customers/{id}/policies route).
  const policiesQ = useQuery({
    queryKey: ["customer-policies", customerId],
    queryFn: async () => {
      const s = await api.get<{ policies: { policy_id: number }[] }>(`/customers/${customerId}/payment-status`);
      // Fetch each policy detail in parallel.
      return Promise.all(s.policies.map((p) => api.get<Policy>(`/policies/${p.policy_id}`)));
    },
    enabled: !!customerId,
  });

  const membersQ = useQuery({
    queryKey: ["members", policyId],
    queryFn: () => api.get<Member[]>(`/members/policy/${policyId}`),
    enabled: !!policyId,
  });

  // Auto-fill premium when policy chosen.
  useEffect(() => {
    if (policiesQ.data && policyId) {
      const p = policiesQ.data.find((pp) => String(pp.id) === policyId);
      if (p && !amount) setAmount(p.premium_amount);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [policyId, policiesQ.data]);

  const mutation = useMutation({
    mutationFn: () => api.post<Payment>("/payments", {
      customer_id: Number(customerId),
      policy_id: Number(policyId),
      member_id: memberId ? Number(memberId) : null,
      amount_paid: amount,
      payment_date: date,
      payment_method: method,
      status: statusVal,
      reference: reference || null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["customer-status", Number(customerId)] });
      qc.invalidateQueries({ queryKey: ["payments", Number(customerId)] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      navigate(`/customers/${customerId}`);
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Failed"),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!customerId || !policyId || !amount) {
      setError("Customer, policy and amount are required.");
      return;
    }
    mutation.mutate();
  }

  return (
    <div className="max-w-2xl space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Record payment</h1>
        <p className="text-sm text-slate-500">Capture a money movement against a policy.</p>
      </div>
      <form onSubmit={submit} className="card p-6 space-y-4">
        <div>
          <label className="label" htmlFor="pay-customer">Customer *</label>
          <select id="pay-customer" className="input" required value={customerId}
                  onChange={(e) => { setCustomerId(e.target.value); setPolicyId(""); setMemberId(""); }}>
            <option value="">Select…</option>
            {customers.data?.map((c) => (
              <option key={c.id} value={c.id}>{c.full_name} ({c.id_number})</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="pay-policy">Policy *</label>
          <select id="pay-policy" className="input" required value={policyId}
                  disabled={!customerId || policiesQ.isLoading}
                  onChange={(e) => { setPolicyId(e.target.value); setMemberId(""); }}>
            <option value="">{customerId ? "Select…" : "Pick a customer first"}</option>
            {policiesQ.data?.map((p) => (
              <option key={p.id} value={p.id}>
                Policy #{p.id} · {p.policy_type} · R{p.premium_amount}
              </option>
            ))}
          </select>
        </div>
        {membersQ.data && membersQ.data.length > 0 && (
          <div>
            <label className="label" htmlFor="pay-member">Member (group scheme)</label>
            <select id="pay-member" className="input" value={memberId} onChange={(e) => setMemberId(e.target.value)}>
              <option value="">— policy-level —</option>
              {membersQ.data.map((m) => (
                <option key={m.id} value={m.id}>{m.full_name}</option>
              ))}
            </select>
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="label" htmlFor="pay-amount">Amount (R) *</label>
            <input id="pay-amount" className="input" type="number" step="0.01" min="0.01" required value={amount}
                   onChange={(e) => setAmount(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="pay-date">Payment date</label>
            <input id="pay-date" className="input" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="pay-method">Method</label>
            <select id="pay-method" className="input" value={method} onChange={(e) => setMethod(e.target.value as any)}>
              <option value="debit_order">Debit order</option>
              <option value="cash">Cash</option>
              <option value="eft">EFT</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="pay-status">Status</label>
            <select id="pay-status" className="input" value={statusVal} onChange={(e) => setStatusVal(e.target.value as any)}>
              <option value="paid">Paid</option>
              <option value="pending">Pending</option>
              <option value="failed">Failed</option>
            </select>
          </div>
        </div>
        <div>
          <label className="label" htmlFor="pay-reference">Reference</label>
          <input id="pay-reference" className="input" value={reference} onChange={(e) => setReference(e.target.value)} placeholder="e.g. bank ref / batch id" />
        </div>
        {error && <div className="text-sm text-red-600 bg-red-50 border border-red-200 px-3 py-2 rounded">{error}</div>}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={() => navigate(-1)}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={mutation.isPending}>
            {mutation.isPending ? "Saving…" : "Record payment"}
          </button>
        </div>
      </form>
    </div>
  );
}
