import { ChangeEvent, FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import { Link, Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import {
  Camera,
  CheckCircle2,
  ChevronLeft,
  Cloud,
  CloudOff,
  LogOut,
  Plus,
  RefreshCcw,
  Share2,
  Smartphone,
  Trash2,
} from "lucide-react";
import {
  drainFieldQueue,
  enrollFieldDevice,
  fetchFieldPlans,
} from "../../field/api";
import {
  clearDraft,
  clearFieldData,
  getDraft,
  getFieldDevice,
  listQueue,
  newClientUuid,
  saveDraft,
  saveFieldDevice,
  saveQueue,
  upsertQueue,
} from "../../field/storage";
import type {
  FieldBeneficiary,
  FieldCoverPlan,
  FieldPendingSubmission,
  FieldPerson,
  FieldSignupDraft,
  FieldSubmissionPayload,
} from "../../field/types";

const PLAN_CACHE_KEY = "mandlzi.field.cover_plans";
const STEPS = ["cover", "holder", "photo", "dependents", "beneficiaries", "payment", "review", "receipt"] as const;
type Step = typeof STEPS[number];

function defaultBeneficiary(): FieldBeneficiary {
  return { relationship_to_holder: "", first_name: "", surname: "", share_pct: "100" };
}

function planNeedsBeneficiaries(plan?: FieldCoverPlan) {
  return plan?.category !== "livestock_benefits";
}

function useOnline() {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  return online;
}

function defaultDraft(): FieldSignupDraft {
  return {
    client_uuid: newClientUuid(),
    local_id: "1",
    cover_plan_id: "",
    holder: { title: "Mr", first_names: "", surname: "", id_number: "", cellphone: "", email: "" },
    dependents: [],
    beneficiaries: [defaultBeneficiary()],
    first_payment_enabled: true,
    first_payment: { amount: "", method: "cash", reference: "" },
    email_receipt_requested: false,
    updated_at: new Date().toISOString(),
  };
}

function readCachedPlans(): FieldCoverPlan[] {
  try {
    const raw = localStorage.getItem(PLAN_CACHE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function writeCachedPlans(plans: FieldCoverPlan[]) {
  localStorage.setItem(PLAN_CACHE_KEY, JSON.stringify(plans));
}

function FieldFrame({ children }: { children: ReactNode }) {
  const online = useOnline();
  const device = getFieldDevice();
  return (
    <div className="min-h-full bg-slate-950 text-slate-100">
      <header className="sticky top-0 z-10 border-b border-slate-800 bg-slate-950/95 backdrop-blur">
        <div className="mx-auto flex max-w-xl items-center justify-between px-4 py-3">
          <Link to="/field" className="flex items-center gap-2 font-semibold">
            <Smartphone size={18} className="text-brand-400" />
            Mandlzi Field
          </Link>
          <div className={`flex items-center gap-1 text-xs ${online ? "text-emerald-300" : "text-amber-300"}`}>
            {online ? <Cloud size={15} /> : <CloudOff size={15} />}
            {online ? "Online" : "Offline"}
          </div>
        </div>
      </header>
      {device && <div className="mx-auto max-w-xl px-4 pt-3 text-xs text-slate-400">{device.name}</div>}
      <main className="mx-auto max-w-xl px-4 py-4">{children}</main>
    </div>
  );
}

function RequireDevice({ children }: { children: ReactNode }) {
  if (!getFieldDevice()) return <Navigate to="/field/enroll" replace />;
  return <>{children}</>;
}

export function FieldApp() {
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/field-sw.js").catch(() => undefined);
    }
  }, []);

  return (
    <FieldFrame>
      <Routes>
        <Route path="enroll" element={<FieldEnrollPage />} />
        <Route index element={<RequireDevice><FieldHomePage /></RequireDevice>} />
        <Route path="signup/:step" element={<RequireDevice><FieldSignupPage /></RequireDevice>} />
        <Route path="sync" element={<RequireDevice><FieldSyncPage /></RequireDevice>} />
        <Route path="settings" element={<RequireDevice><FieldSettingsPage /></RequireDevice>} />
        <Route path="*" element={<Navigate to="/field" replace />} />
      </Routes>
    </FieldFrame>
  );
}

function FieldEnrollPage() {
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const device = await enrollFieldDevice(code, name);
      saveFieldDevice(device);
      navigate("/field", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Enrollment failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5 pt-8">
      <div>
        <h1 className="text-2xl font-semibold">Enroll phone</h1>
        <p className="mt-1 text-sm text-slate-400">Enter the code from the admin dashboard.</p>
      </div>
      <div className="space-y-3">
        <label className="block text-sm font-medium text-slate-200" htmlFor="field-code">Code</label>
        <input
          id="field-code"
          className="input text-lg uppercase tracking-widest"
          autoCapitalize="characters"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          required
        />
        <label className="block text-sm font-medium text-slate-200" htmlFor="field-name">Phone name</label>
        <input id="field-name" className="input" value={name} onChange={(e) => setName(e.target.value)} required />
      </div>
      {error && <div className="rounded-md border border-red-800 bg-red-950 px-3 py-2 text-sm text-red-100">{error}</div>}
      <button className="btn-primary w-full" disabled={saving}>{saving ? "Enrolling..." : "Enroll"}</button>
    </form>
  );
}

function FieldHomePage() {
  const navigate = useNavigate();
  const [plans, setPlans] = useState<FieldCoverPlan[]>(readCachedPlans);
  const [queue, setQueue] = useState<FieldPendingSubmission[]>(listQueue);
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    fetchFieldPlans()
      .then((items) => {
        setPlans(items);
        writeCachedPlans(items);
      })
      .catch(() => undefined);
  }, []);

  async function syncNow() {
    setSyncing(true);
    try {
      setQueue(await drainFieldQueue());
    } finally {
      setSyncing(false);
    }
  }

  const pending = queue.filter((q) => q.status !== "synced").length;

  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-slate-800 bg-slate-900 p-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold">Capture signup</h1>
            <p className="text-sm text-slate-400">{plans.length} cover plans cached</p>
          </div>
          {pending > 0 && <span className="rounded-full bg-amber-500 px-2 py-1 text-xs font-semibold text-slate-950">{pending} pending</span>}
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2">
          <button className="btn-primary" onClick={() => {
            const draft = getDraft() || defaultDraft();
            saveDraft(draft);
            navigate("/field/signup/cover");
          }}>
            <Plus size={16} /> New
          </button>
          <Link to="/field/sync" className="btn-secondary">Sync</Link>
        </div>
      </section>

      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-300">Queue</h2>
          <button className="btn-secondary" onClick={syncNow} disabled={syncing}>
            <RefreshCcw size={15} /> {syncing ? "Syncing" : "Sync now"}
          </button>
        </div>
        {queue.length === 0 ? (
          <div className="rounded-lg border border-slate-800 p-4 text-sm text-slate-400">No pending submissions.</div>
        ) : queue.slice(0, 4).map((row) => <QueueRow key={row.client_uuid} row={row} />)}
      </section>

      <div className="flex gap-2">
        <Link className="btn-secondary flex-1" to="/field/settings">Settings</Link>
      </div>
    </div>
  );
}

function QueueRow({ row }: { row: FieldPendingSubmission }) {
  const color = row.status === "synced" ? "text-emerald-300" : row.status === "failed" ? "text-red-300" : "text-amber-300";
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-mono text-xs text-slate-400">{row.client_uuid}</div>
          <div className={`text-sm font-semibold ${color}`}>{row.status}</div>
        </div>
        {row.status === "synced" && <CheckCircle2 className="text-emerald-300" size={18} />}
      </div>
      {row.last_error && <div className="mt-2 text-xs text-red-200">{row.last_error}</div>}
    </div>
  );
}

function FieldSignupPage() {
  const { step = "cover" } = useParams();
  const navigate = useNavigate();
  const [plans, setPlans] = useState<FieldCoverPlan[]>(readCachedPlans);
  const [draft, setDraftState] = useState<FieldSignupDraft>(() => getDraft() || defaultDraft());

  useEffect(() => {
    fetchFieldPlans()
      .then((items) => {
        setPlans(items);
        writeCachedPlans(items);
      })
      .catch(() => undefined);
  }, []);

  function setDraft(next: FieldSignupDraft) {
    const value = { ...next, updated_at: new Date().toISOString() };
    setDraftState(value);
    saveDraft(value);
  }

  const currentStep = STEPS.includes(step as Step) ? (step as Step) : "cover";
  const idx = STEPS.indexOf(currentStep);
  const selectedPlan = plans.find((p) => p.id === Number(draft.cover_plan_id));

  function go(next: Step) {
    navigate(`/field/signup/${next}`);
  }

  function next() {
    go(STEPS[Math.min(idx + 1, STEPS.length - 1)]);
  }

  function back() {
    if (idx === 0) navigate("/field");
    else go(STEPS[idx - 1]);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button className="btn-secondary" onClick={back}><ChevronLeft size={16} /> Back</button>
        <div className="text-xs text-slate-400">{idx + 1} / {STEPS.length}</div>
      </div>
      <div className="h-1 rounded-full bg-slate-800">
        <div className="h-1 rounded-full bg-brand-500" style={{ width: `${((idx + 1) / STEPS.length) * 100}%` }} />
      </div>

      {currentStep === "cover" && <CoverStep plans={plans} draft={draft} setDraft={setDraft} next={next} />}
      {currentStep === "holder" && <HolderStep draft={draft} setDraft={setDraft} next={next} />}
      {currentStep === "photo" && <PhotoStep draft={draft} setDraft={setDraft} next={next} />}
      {currentStep === "dependents" && <DependentsStep draft={draft} setDraft={setDraft} next={next} plan={selectedPlan} />}
      {currentStep === "beneficiaries" && <BeneficiariesStep draft={draft} setDraft={setDraft} next={next} plan={selectedPlan} />}
      {currentStep === "payment" && <PaymentStep draft={draft} setDraft={setDraft} next={next} plan={selectedPlan} />}
      {currentStep === "review" && <ReviewStep draft={draft} plan={selectedPlan} />}
      {currentStep === "receipt" && <ReceiptStep draft={draft} plan={selectedPlan} />}
    </div>
  );
}

function CoverStep({ plans, draft, setDraft, next }: StepProps & { plans: FieldCoverPlan[] }) {
  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); next(); }}>
      <h1 className="text-xl font-semibold">Cover plan</h1>
      <select
        className="input"
        value={draft.cover_plan_id}
        required
        onChange={(e) => {
          const coverPlanId = e.target.value ? Number(e.target.value) : "";
          const plan = plans.find((p) => p.id === coverPlanId);
          const maxDependents = plan?.max_dependents ?? draft.dependents.length;
          const needsBeneficiaries = planNeedsBeneficiaries(plan);
          setDraft({
            ...draft,
            cover_plan_id: coverPlanId,
            dependents: draft.dependents.slice(0, maxDependents),
            beneficiaries: needsBeneficiaries
              ? (draft.beneficiaries.length ? draft.beneficiaries : [defaultBeneficiary()])
              : [],
            first_payment: { ...draft.first_payment, amount: plan?.monthly_premium || draft.first_payment.amount },
          });
        }}
      >
        <option value="">Select a plan</option>
        {plans.map((plan) => (
          <option key={plan.id} value={plan.id}>{plan.cover_type} - R{plan.monthly_premium}</option>
        ))}
      </select>
      <button className="btn-primary w-full">Continue</button>
    </form>
  );
}

interface StepProps {
  draft: FieldSignupDraft;
  setDraft: (draft: FieldSignupDraft) => void;
  next: () => void;
}

function HolderStep({ draft, setDraft, next }: StepProps) {
  const h = draft.holder;
  const update = (patch: Partial<FieldPerson>) => setDraft({ ...draft, holder: { ...h, ...patch } });
  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); next(); }}>
      <h1 className="text-xl font-semibold">Policy holder</h1>
      <PersonFields person={h} update={update} requireId />
      <button className="btn-primary w-full">Continue</button>
    </form>
  );
}

function PersonFields({ person, update, requireId, relationship }: {
  person: FieldPerson;
  update: (patch: Partial<FieldPerson>) => void;
  requireId?: boolean;
  relationship?: boolean;
}) {
  return (
    <div className="grid grid-cols-1 gap-3">
      <div className="grid grid-cols-3 gap-2">
        <select className="input" value={person.title || "Mr"} onChange={(e) => update({ title: e.target.value })}>
          {["Mr", "Mrs", "Ms", "Dr"].map((v) => <option key={v}>{v}</option>)}
        </select>
        <input className="input col-span-2" placeholder="First names" value={person.first_names || ""} onChange={(e) => update({ first_names: e.target.value })} required />
      </div>
      <input className="input" placeholder="Surname" value={person.surname || ""} onChange={(e) => update({ surname: e.target.value })} required />
      {requireId && <input className="input" placeholder="ID number" value={person.id_number || ""} onChange={(e) => update({ id_number: e.target.value })} required />}
      {relationship && <input className="input" placeholder="Relationship" value={person.relationship_to_holder || ""} onChange={(e) => update({ relationship_to_holder: e.target.value })} required />}
      <div className="grid grid-cols-2 gap-2">
        <input className="input" placeholder="Cellphone" value={person.cellphone || ""} onChange={(e) => update({ cellphone: e.target.value })} />
        <input className="input" placeholder="Email" type="email" value={person.email || ""} onChange={(e) => update({ email: e.target.value })} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <select className="input" value={person.gender || ""} onChange={(e) => update({ gender: e.target.value })}>
          <option value="">Gender</option>
          <option value="female">Female</option>
          <option value="male">Male</option>
          <option value="other">Other</option>
        </select>
        <input className="input" type="date" value={person.date_of_birth || ""} onChange={(e) => update({ date_of_birth: e.target.value })} />
      </div>
      <input className="input" placeholder="Nationality" value={person.nationality || ""} onChange={(e) => update({ nationality: e.target.value })} />
    </div>
  );
}

function PhotoStep({ draft, setDraft, next }: StepProps) {
  const [busy, setBusy] = useState(false);
  async function pickPhoto(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      const dataUrl = await resizeImage(file);
      setDraft({ ...draft, photo_data_url: dataUrl, id_photo_id: undefined });
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">ID photo</h1>
      <label className="flex min-h-44 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-slate-700 bg-slate-900 p-4 text-center">
        {draft.photo_data_url ? (
          <img src={draft.photo_data_url} alt="Captured ID" className="max-h-64 rounded-md object-contain" />
        ) : (
          <>
            <Camera size={28} className="mb-2 text-brand-300" />
            <span className="text-sm text-slate-300">{busy ? "Preparing photo..." : "Tap to capture ID photo"}</span>
          </>
        )}
        <input className="hidden" type="file" accept="image/*" capture="environment" onChange={pickPhoto} />
      </label>
      <button className="btn-primary w-full" onClick={next} disabled={!draft.photo_data_url}>Use photo</button>
      <button className="btn-secondary w-full" onClick={next}>Skip for now</button>
    </div>
  );
}

function DependentsStep({ draft, setDraft, next, plan }: StepProps & { plan?: FieldCoverPlan }) {
  const maxDependents = plan?.max_dependents;
  const canAdd = maxDependents === undefined || draft.dependents.length < maxDependents;
  const update = (index: number, patch: Partial<FieldPerson>) => {
    const dependents = draft.dependents.map((d, i) => i === index ? { ...d, ...patch } : d);
    setDraft({ ...draft, dependents });
  };
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Dependents</h1>
        {maxDependents !== undefined && <span className="text-sm text-slate-400">{draft.dependents.length} / {maxDependents}</span>}
      </div>
      {draft.dependents.map((dep, index) => (
        <div key={index} className="rounded-lg border border-slate-800 bg-slate-900 p-3">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-sm font-semibold">Dependent {index + 1}</span>
            <button className="btn-secondary" onClick={() => setDraft({ ...draft, dependents: draft.dependents.filter((_, i) => i !== index) })}><Trash2 size={15} /></button>
          </div>
          <PersonFields person={dep} update={(patch) => update(index, patch)} relationship />
        </div>
      ))}
      {maxDependents === 0 && (
        <div className="rounded-lg border border-slate-800 p-4 text-sm text-slate-400">This plan has no dependents.</div>
      )}
      <button
        className="btn-secondary w-full"
        disabled={!canAdd}
        onClick={() => setDraft({ ...draft, dependents: [...draft.dependents, { title: "Ms", first_names: "", surname: "", relationship_to_holder: "" }] })}
      >
        <Plus size={16} /> Add dependent
      </button>
      <button className="btn-primary w-full" onClick={next}>Continue</button>
    </div>
  );
}

function BeneficiariesStep({ draft, setDraft, next, plan }: StepProps & { plan?: FieldCoverPlan }) {
  const total = useMemo(() => draft.beneficiaries.reduce((sum, b) => sum + Number(b.share_pct || 0), 0), [draft.beneficiaries]);
  const needsBeneficiaries = planNeedsBeneficiaries(plan);
  const update = (index: number, patch: Partial<FieldBeneficiary>) => {
    const beneficiaries = draft.beneficiaries.map((b, i) => i === index ? { ...b, ...patch } : b);
    setDraft({ ...draft, beneficiaries });
  };
  const canContinue = !needsBeneficiaries || (draft.beneficiaries.length > 0 && Math.abs(total - 100) < 0.01);
  const continueStep = () => {
    if (!needsBeneficiaries && draft.beneficiaries.length) {
      setDraft({ ...draft, beneficiaries: [] });
    }
    next();
  };
  if (!needsBeneficiaries) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-semibold">Beneficiaries</h1>
        <div className="rounded-lg border border-slate-800 p-4 text-sm text-slate-400">This plan does not use beneficiaries.</div>
        <button className="btn-primary w-full" onClick={continueStep}>Continue</button>
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Beneficiaries</h1>
        <span className={canContinue ? "text-sm text-emerald-300" : "text-sm text-amber-300"}>{total.toFixed(2)}%</span>
      </div>
      {draft.beneficiaries.map((ben, index) => (
        <div key={index} className="rounded-lg border border-slate-800 bg-slate-900 p-3">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-sm font-semibold">Beneficiary {index + 1}</span>
            <button className="btn-secondary" onClick={() => setDraft({ ...draft, beneficiaries: draft.beneficiaries.filter((_, i) => i !== index) })}><Trash2 size={15} /></button>
          </div>
          <div className="grid grid-cols-1 gap-3">
            <input className="input" placeholder="Relationship" value={ben.relationship_to_holder} onChange={(e) => update(index, { relationship_to_holder: e.target.value })} required />
            <div className="grid grid-cols-3 gap-2">
              <select className="input" value={ben.title || ""} onChange={(e) => update(index, { title: e.target.value })}>
                <option value="">Title</option>
                {["Mr", "Mrs", "Ms", "Dr"].map((v) => <option key={v}>{v}</option>)}
              </select>
              <input className="input col-span-2" placeholder="First name" value={ben.first_name} onChange={(e) => update(index, { first_name: e.target.value })} required />
            </div>
            <input className="input" placeholder="Surname" value={ben.surname} onChange={(e) => update(index, { surname: e.target.value })} required />
            <div className="grid grid-cols-2 gap-2">
              <input className="input" type="email" placeholder="Email" value={ben.email || ""} onChange={(e) => update(index, { email: e.target.value })} />
              <input className="input" placeholder="Cellphone" value={ben.cellphone || ""} onChange={(e) => update(index, { cellphone: e.target.value })} />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <input className="input" type="date" value={ben.date_of_birth || ""} onChange={(e) => update(index, { date_of_birth: e.target.value })} />
              <input className="input" placeholder="Share %" inputMode="decimal" value={ben.share_pct} onChange={(e) => update(index, { share_pct: e.target.value })} required />
            </div>
            <input className="input" placeholder="Nationality" value={ben.nationality || ""} onChange={(e) => update(index, { nationality: e.target.value })} />
          </div>
        </div>
      ))}
      <button className="btn-secondary w-full" onClick={() => setDraft({ ...draft, beneficiaries: [...draft.beneficiaries, { relationship_to_holder: "", first_name: "", surname: "", share_pct: "0" }] })}>
        <Plus size={16} /> Add beneficiary
      </button>
      <button className="btn-primary w-full" disabled={!canContinue} onClick={continueStep}>Continue</button>
    </div>
  );
}

function PaymentStep({ draft, setDraft, next, plan }: StepProps & { plan?: FieldCoverPlan }) {
  const amount = draft.first_payment.amount || plan?.monthly_premium || "";
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">First payment</h1>
      <label className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900 p-3">
        <span className="text-sm font-medium">Payment received</span>
        <input type="checkbox" checked={draft.first_payment_enabled} onChange={(e) => setDraft({ ...draft, first_payment_enabled: e.target.checked })} />
      </label>
      {draft.first_payment_enabled && (
        <div className="grid grid-cols-1 gap-3">
          <input className="input" inputMode="decimal" placeholder="Amount" value={amount} onChange={(e) => setDraft({ ...draft, first_payment: { ...draft.first_payment, amount: e.target.value } })} />
          <select className="input" value={draft.first_payment.method} onChange={(e) => setDraft({ ...draft, first_payment: { ...draft.first_payment, method: e.target.value as any } })}>
            <option value="cash">Cash</option>
            <option value="eft">EFT</option>
            <option value="debit_order">Debit order</option>
          </select>
          <input className="input" placeholder="Reference" value={draft.first_payment.reference} onChange={(e) => setDraft({ ...draft, first_payment: { ...draft.first_payment, reference: e.target.value } })} />
          <label className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900 p-3">
            <span className="text-sm font-medium">Email receipt</span>
            <input type="checkbox" checked={draft.email_receipt_requested} onChange={(e) => setDraft({ ...draft, email_receipt_requested: e.target.checked })} />
          </label>
        </div>
      )}
      <button className="btn-primary w-full" onClick={() => {
        setDraft({ ...draft, first_payment: { ...draft.first_payment, amount } });
        next();
      }}>Continue</button>
    </div>
  );
}

function ReviewStep({ draft, plan }: { draft: FieldSignupDraft; plan?: FieldCoverPlan }) {
  const navigate = useNavigate();
  function queueSubmission() {
    const payload = buildPayload(draft);
    const row: FieldPendingSubmission = {
      client_uuid: draft.client_uuid,
      payload,
      photo_data_url: draft.photo_data_url,
      status: "queued",
      attempts: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    upsertQueue(row);
    clearDraft();
    drainFieldQueue().catch(() => undefined);
    navigate("/field/signup/receipt");
  }
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Review</h1>
      <div className="rounded-lg border border-slate-800 bg-slate-900 p-4 text-sm">
        <div className="font-semibold">{draft.holder.first_names} {draft.holder.surname}</div>
        <div className="text-slate-400">{draft.holder.id_number}</div>
        <dl className="mt-3 grid grid-cols-2 gap-2">
          <dt className="text-slate-400">Plan</dt><dd>{plan?.cover_type || "Selected plan"}</dd>
          <dt className="text-slate-400">Dependents</dt><dd>{draft.dependents.length}</dd>
          <dt className="text-slate-400">Beneficiaries</dt><dd>{draft.beneficiaries.length}</dd>
          <dt className="text-slate-400">Payment</dt><dd>{draft.first_payment_enabled ? `R${draft.first_payment.amount}` : "None"}</dd>
        </dl>
      </div>
      <button className="btn-primary w-full" onClick={queueSubmission}>Queue signup</button>
    </div>
  );
}

function ReceiptStep({ draft, plan }: { draft: FieldSignupDraft; plan?: FieldCoverPlan }) {
  const last = listQueue()[0];
  const text = `Mandlzi receipt\nReference: ${draft.client_uuid.slice(0, 8)}\nHolder: ${draft.holder.first_names} ${draft.holder.surname}\nPlan: ${plan?.cover_type || ""}\nAmount: R${draft.first_payment.amount || "0.00"}`;
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-emerald-800 bg-emerald-950 p-4">
        <h1 className="text-xl font-semibold">Signup queued</h1>
        <p className="mt-1 text-sm text-emerald-100">Reference {draft.client_uuid.slice(0, 8)}</p>
      </div>
      <pre className="whitespace-pre-wrap rounded-lg border border-slate-800 bg-white p-4 text-sm text-slate-900">{text}</pre>
      <button className="btn-primary w-full" onClick={() => {
        if (navigator.share) navigator.share({ title: "Mandlzi receipt", text }).catch(() => undefined);
      }}>
        <Share2 size={16} /> Share receipt
      </button>
      {last?.status && <QueueRow row={last} />}
      <Link className="btn-secondary w-full" to="/field">Home</Link>
    </div>
  );
}

function buildPayload(draft: FieldSignupDraft): FieldSubmissionPayload {
  const clean = (obj: Record<string, any>) => Object.fromEntries(
    Object.entries(obj).map(([k, v]) => [k, v === "" ? null : v]),
  ) as Record<string, string | null>;
  return {
    client_uuid: draft.client_uuid,
    signups: [{
      local_id: draft.local_id,
      cover_plan_id: Number(draft.cover_plan_id),
      holder: clean(draft.holder),
      id_photo_id: draft.id_photo_id,
      dependents: draft.dependents.map((d) => clean(d)),
      beneficiaries: draft.beneficiaries.map((b) => clean(b as any)),
      first_payment: draft.first_payment_enabled ? {
        amount: draft.first_payment.amount,
        method: draft.first_payment.method,
        reference: draft.first_payment.reference || null,
      } : undefined,
      email_receipt_requested: draft.email_receipt_requested,
    }],
  };
}

function FieldSyncPage() {
  const [queue, setQueue] = useState<FieldPendingSubmission[]>(listQueue);
  const [syncing, setSyncing] = useState(false);
  async function sync() {
    setSyncing(true);
    try {
      setQueue(await drainFieldQueue());
    } finally {
      setSyncing(false);
    }
  }
  function clearSynced() {
    const rows = queue.filter((q) => q.status !== "synced");
    saveQueue(rows);
    setQueue(rows);
  }
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Sync</h1>
      <div className="grid grid-cols-2 gap-2">
        <button className="btn-primary" onClick={sync} disabled={syncing}><RefreshCcw size={16} /> {syncing ? "Syncing" : "Sync now"}</button>
        <button className="btn-secondary" onClick={clearSynced}>Clear synced</button>
      </div>
      {queue.length === 0 ? <div className="rounded-lg border border-slate-800 p-4 text-sm text-slate-400">Queue is empty.</div> : queue.map((row) => <QueueRow key={row.client_uuid} row={row} />)}
    </div>
  );
}

function FieldSettingsPage() {
  const navigate = useNavigate();
  const device = getFieldDevice();
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Settings</h1>
      <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
        <div className="text-sm text-slate-400">Device</div>
        <div className="font-semibold">{device?.name}</div>
        <div className="font-mono text-xs text-slate-500">#{device?.device_id}</div>
      </div>
      <button className="btn-danger w-full" onClick={() => {
        clearFieldData();
        navigate("/field/enroll", { replace: true });
      }}>
        <LogOut size={16} /> Reset enrollment
      </button>
    </div>
  );
}

function resizeImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const scale = Math.min(1, 1024 / Math.max(img.width, img.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        reject(new Error("Canvas is unavailable"));
        return;
      }
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      resolve(canvas.toDataURL("image/jpeg", 0.72));
    };
    img.onerror = () => reject(new Error("Could not read image"));
    img.src = URL.createObjectURL(file);
  });
}
