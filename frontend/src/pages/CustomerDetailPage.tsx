import { useId, useState, FormEvent } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Plus, Trash2, Users } from "lucide-react";
import { api, ApiError } from "../api/client";
import type {
  Customer, Policy, Payment, CustomerPaymentStatusResponse, Member, MemberPaymentStatus,
} from "../types";
import { StatusBadge } from "../components/StatusBadge";
import { formatDate, formatMoney, formatMonth } from "../utils";
import { useAuth } from "../auth/AuthContext";

export function CustomerDetailPage() {
  const { id } = useParams();
  const customerId = Number(id);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { canWrite, canAdmin } = useAuth();
  const [showPolicyForm, setShowPolicyForm] = useState(false);

  const customerQ = useQuery({
    queryKey: ["customer", customerId],
    queryFn: () => api.get<Customer>(`/customers/${customerId}`),
    enabled: !!customerId,
  });
  const statusQ = useQuery({
    queryKey: ["customer-status", customerId],
    queryFn: () => api.get<CustomerPaymentStatusResponse>(`/customers/${customerId}/payment-status`),
    enabled: !!customerId,
  });
  const paymentsQ = useQuery({
    queryKey: ["payments", customerId],
    queryFn: () => api.get<Payment[]>(`/payments?customer_id=${customerId}`),
    enabled: !!customerId,
  });

  const deleteMut = useMutation({
    mutationFn: () => api.delete(`/customers/${customerId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["customers"] });
      navigate("/customers");
    },
  });

  if (customerQ.isLoading) return <div className="text-slate-500">Loading…</div>;
  if (customerQ.error) return <div className="text-red-600">Customer not found.</div>;
  const customer = customerQ.data!;
  const status = statusQ.data;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/customers" className="text-slate-500 hover:text-slate-700"><ArrowLeft size={18} /></Link>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">{customer.full_name}</h1>
            <p className="text-sm text-slate-500">{customer.id_number} · {customer.email || "no email"}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={customer.status} />
          {status && <StatusBadge status={status.overall_status} />}
          {canAdmin && (
            <button
              className="btn-danger"
              onClick={() => { if (confirm("Delete this customer? This cascades to all policies/payments.")) deleteMut.mutate(); }}
              disabled={deleteMut.isPending}
            >
              <Trash2 size={14} /> Delete
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="card p-5">
          <div className="text-xs uppercase text-slate-500 font-semibold">Phone</div>
          <div className="text-slate-800">{customer.phone || "—"}</div>
        </div>
        <div className="card p-5">
          <div className="text-xs uppercase text-slate-500 font-semibold">Created</div>
          <div className="text-slate-800">{formatDate(customer.created_at)}</div>
        </div>
        <div className="card p-5">
          <div className="text-xs uppercase text-slate-500 font-semibold">Total outstanding</div>
          <div className="text-slate-800 font-bold text-lg">
            {status ? formatMoney(status.policies.reduce((acc, p) => acc + parseFloat(p.total_outstanding), 0)) : "—"}
          </div>
        </div>
      </div>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Policies</h2>
          {canWrite && (
            <button className="btn-secondary" onClick={() => setShowPolicyForm((v) => !v)}>
              <Plus size={14} /> {showPolicyForm ? "Cancel" : "Add policy"}
            </button>
          )}
        </div>
        {showPolicyForm && <NewPolicyForm customerId={customer.id} onDone={() => setShowPolicyForm(false)} />}
        <div className="space-y-3">
          {status?.policies.length === 0 && (
            <div className="card p-5 text-sm text-slate-500">No policies yet.</div>
          )}
          {status?.policies.map((ps) => (
            <PolicyBlock key={ps.policy_id} customerId={customer.id} ps={ps} />
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Payments</h2>
        <div className="card overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <th className="table-th">Date</th>
                <th className="table-th">Policy</th>
                <th className="table-th">Method</th>
                <th className="table-th">Amount</th>
                <th className="table-th">Status</th>
                <th className="table-th">Reference</th>
              </tr>
            </thead>
            <tbody>
              {paymentsQ.data?.length === 0 && (
                <tr><td className="table-td text-slate-500" colSpan={6}>No payments yet.</td></tr>
              )}
              {paymentsQ.data?.map((p) => (
                <tr key={p.id}>
                  <td className="table-td">{formatDate(p.payment_date)}</td>
                  <td className="table-td">#{p.policy_id}</td>
                  <td className="table-td">{p.payment_method}</td>
                  <td className="table-td font-medium">{formatMoney(p.amount_paid)}</td>
                  <td className="table-td"><StatusBadge status={p.status} /></td>
                  <td className="table-td text-slate-500">{p.reference || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function PolicyBlock({ customerId, ps }: { customerId: number; ps: CustomerPaymentStatusResponse["policies"][number] }) {
  const policyQ = useQuery({
    queryKey: ["policy", ps.policy_id],
    queryFn: () => api.get<Policy>(`/policies/${ps.policy_id}`),
  });
  const policy = policyQ.data;
  const isGroup = policy?.policy_type === "group_scheme";

  return (
    <div className="card p-5">
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-semibold">Policy #{ps.policy_id}</h3>
            <StatusBadge status={ps.status} />
            {isGroup && <span className="text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded ring-1 ring-indigo-200">Group scheme</span>}
          </div>
          <div className="text-sm text-slate-500 mt-1">
            {policy && <>Premium {formatMoney(policy.premium_amount)} · monthly · started {formatDate(policy.start_date)}</>}
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs uppercase text-slate-500 font-semibold">Outstanding</div>
          <div className="font-bold text-lg">{formatMoney(ps.total_outstanding)}</div>
          <div className="text-xs text-slate-500">{ps.months_in_arrears} month(s) in arrears</div>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2">
        {ps.months.slice(-12).map((m) => (
          <div key={m.month} className="rounded border border-slate-100 p-2 text-center">
            <div className="text-[11px] text-slate-500">{formatMonth(m.month)}</div>
            <StatusBadge status={m.status} />
            <div className="text-[11px] text-slate-500 mt-1">{formatMoney(m.paid_amount)} / {formatMoney(m.expected_amount)}</div>
          </div>
        ))}
      </div>

      {isGroup && policy && <GroupSchemeBlock customerId={customerId} policyId={policy.id} />}
    </div>
  );
}

function GroupSchemeBlock({ customerId, policyId }: { customerId: number; policyId: number }) {
  const { canWrite } = useAuth();
  const [showForm, setShowForm] = useState(false);
  const membersQ = useQuery({
    queryKey: ["members", policyId],
    queryFn: () => api.get<Member[]>(`/members/policy/${policyId}`),
  });
  const statusQ = useQuery({
    queryKey: ["members-status", policyId],
    queryFn: () => api.get<MemberPaymentStatus[]>(`/members/policy/${policyId}/payment-status`),
  });
  const statusByMember = new Map((statusQ.data || []).map((s) => [s.member_id, s]));

  return (
    <div className="mt-4 border-t border-slate-100 pt-4">
      <div className="flex items-center justify-between mb-2">
        <h4 className="font-semibold flex items-center gap-2 text-slate-700"><Users size={14} /> Group members</h4>
        {canWrite && (
          <button className="btn-secondary text-xs" onClick={() => setShowForm((v) => !v)}>
            <Plus size={12} /> {showForm ? "Cancel" : "Add member"}
          </button>
        )}
      </div>
      {showForm && <NewMemberForm policyId={policyId} onDone={() => setShowForm(false)} />}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th className="table-th">Name</th>
              <th className="table-th">Relationship</th>
              <th className="table-th">Contribution</th>
              <th className="table-th">Status</th>
              <th className="table-th">Arrears</th>
            </tr>
          </thead>
          <tbody>
            {membersQ.data?.length === 0 && (
              <tr><td className="table-td text-slate-500" colSpan={5}>No members yet.</td></tr>
            )}
            {membersQ.data?.map((m) => {
              const s = statusByMember.get(m.id);
              return (
                <tr key={m.id}>
                  <td className="table-td font-medium">{m.full_name}</td>
                  <td className="table-td">{m.relationship_to_holder || "—"}</td>
                  <td className="table-td">{m.contribution_amount ? formatMoney(m.contribution_amount) : "—"}</td>
                  <td className="table-td">{s ? <StatusBadge status={s.status} /> : "—"}</td>
                  <td className="table-td">{s ? `${s.months_in_arrears} mo · ${formatMoney(s.total_outstanding)}` : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function NewPolicyForm({ customerId, onDone }: { customerId: number; onDone: () => void }) {
  const qc = useQueryClient();
  const baseId = useId();
  const ids = {
    type: `${baseId}-type`,
    premium: `${baseId}-premium`,
    start: `${baseId}-start`,
    grace: `${baseId}-grace`,
    lapse: `${baseId}-lapse`,
  };
  const [premium, setPremium] = useState("150.00");
  const [type, setType] = useState<"individual" | "group_scheme">("individual");
  const [startDate, setStartDate] = useState<string>(() => new Date().toISOString().slice(0, 10));
  const [grace, setGrace] = useState<string>("");
  const [lapse, setLapse] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () => api.post<Policy>("/policies", {
      customer_id: customerId,
      policy_type: type,
      premium_amount: premium,
      billing_cycle: "monthly",
      start_date: startDate,
      grace_period_days: grace ? Number(grace) : null,
      lapse_threshold_months: lapse ? Number(lapse) : null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["customer-status", customerId] });
      onDone();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Failed"),
  });

  return (
    <form onSubmit={(e) => { e.preventDefault(); m.mutate(); }} className="card p-4 space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
        <div>
          <label className="label" htmlFor={ids.type}>Type</label>
          <select id={ids.type} className="input" value={type} onChange={(e) => setType(e.target.value as any)}>
            <option value="individual">Individual</option>
            <option value="group_scheme">Group scheme</option>
          </select>
        </div>
        <div>
          <label className="label" htmlFor={ids.premium}>Premium (R)</label>
          <input id={ids.premium} className="input" type="number" step="0.01" min="0.01" required value={premium} onChange={(e) => setPremium(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor={ids.start}>Start date</label>
          <input id={ids.start} className="input" type="date" required value={startDate} onChange={(e) => setStartDate(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor={ids.grace}>Grace days (optional)</label>
          <input id={ids.grace} className="input" type="number" min="0" value={grace} onChange={(e) => setGrace(e.target.value)} placeholder="30" />
        </div>
        <div>
          <label className="label" htmlFor={ids.lapse}>Lapse threshold months (optional)</label>
          <input id={ids.lapse} className="input" type="number" min="1" value={lapse} onChange={(e) => setLapse(e.target.value)} placeholder="3" />
        </div>
      </div>
      {error && <div className="text-sm text-red-600">{error}</div>}
      <div className="flex justify-end gap-2">
        <button type="button" className="btn-secondary" onClick={onDone}>Cancel</button>
        <button className="btn-primary" disabled={m.isPending}>{m.isPending ? "Saving…" : "Create policy"}</button>
      </div>
    </form>
  );
}

function NewMemberForm({ policyId, onDone }: { policyId: number; onDone: () => void }) {
  const qc = useQueryClient();
  const baseId = useId();
  const ids = {
    name: `${baseId}-name`,
    rel: `${baseId}-rel`,
    contrib: `${baseId}-contrib`,
  };
  const [form, setForm] = useState({ full_name: "", relationship_to_holder: "", contribution_amount: "" });
  const [error, setError] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () => api.post<Member>("/members", {
      policy_id: policyId,
      full_name: form.full_name,
      relationship_to_holder: form.relationship_to_holder || null,
      contribution_amount: form.contribution_amount || null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["members", policyId] });
      qc.invalidateQueries({ queryKey: ["members-status", policyId] });
      onDone();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Failed"),
  });
  return (
    <form onSubmit={(e) => { e.preventDefault(); m.mutate(); }} className="card p-4 space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label className="label" htmlFor={ids.name}>Full name *</label>
          <input id={ids.name} className="input" required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        </div>
        <div>
          <label className="label" htmlFor={ids.rel}>Relationship</label>
          <input id={ids.rel} className="input" value={form.relationship_to_holder} onChange={(e) => setForm({ ...form, relationship_to_holder: e.target.value })} placeholder="spouse, child, …" />
        </div>
        <div>
          <label className="label" htmlFor={ids.contrib}>Contribution (R)</label>
          <input id={ids.contrib} className="input" type="number" step="0.01" min="0" value={form.contribution_amount} onChange={(e) => setForm({ ...form, contribution_amount: e.target.value })} />
        </div>
      </div>
      {error && <div className="text-sm text-red-600">{error}</div>}
      <div className="flex justify-end gap-2">
        <button type="button" className="btn-secondary" onClick={onDone}>Cancel</button>
        <button className="btn-primary" disabled={m.isPending}>{m.isPending ? "Saving…" : "Add member"}</button>
      </div>
    </form>
  );
}
