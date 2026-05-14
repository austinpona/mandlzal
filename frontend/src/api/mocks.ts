// Demo-only in-memory mock backend. Activated when VITE_DEMO=true.
// Keeps the UI clickable for client demos without a real FastAPI server.
import type {
  AuditLogItem,
  Customer,
  CustomerPaymentStatusResponse,
  DashboardSummary,
  Member,
  MemberPaymentStatus,
  NotificationItem,
  Payment,
  Policy,
  User,
} from "../types";
import { ApiError } from "./client";

type Method = "GET" | "POST" | "PATCH" | "DELETE";

const now = () => new Date().toISOString();
const today = () => new Date().toISOString().slice(0, 10);

let nextId = 1000;
const id = () => ++nextId;

const demoUser: User = {
  id: 1,
  email: "admin@example.com",
  full_name: "Demo Admin",
  is_admin: true,
  role: "admin",
};

const customers: Customer[] = [
  {
    id: 1,
    full_name: "Thandi Mokoena",
    id_number: "8501015009087",
    phone: "+27 82 555 0101",
    email: "thandi@example.com",
    status: "active",
    created_at: "2025-09-12T10:00:00Z",
    updated_at: "2025-09-12T10:00:00Z",
  },
  {
    id: 2,
    full_name: "Sipho Dlamini",
    id_number: "7806145122080",
    phone: "+27 83 555 0202",
    email: null,
    status: "active",
    created_at: "2025-10-04T08:30:00Z",
    updated_at: "2025-10-04T08:30:00Z",
  },
  {
    id: 3,
    full_name: "Nomvula Khumalo",
    id_number: "9203228899084",
    phone: null,
    email: "nomvula@example.com",
    status: "lapsed",
    created_at: "2025-08-21T14:12:00Z",
    updated_at: "2026-03-01T09:00:00Z",
  },
  {
    id: 4,
    full_name: "Bongani Zulu",
    id_number: "8011305544087",
    phone: "+27 84 555 0404",
    email: "bongani@example.com",
    status: "active",
    created_at: "2025-11-19T11:45:00Z",
    updated_at: "2025-11-19T11:45:00Z",
  },
  {
    id: 5,
    full_name: "Lerato Naidoo",
    id_number: "9505198811086",
    phone: "+27 81 555 0505",
    email: null,
    status: "cancelled",
    created_at: "2025-07-02T07:20:00Z",
    updated_at: "2026-01-15T16:00:00Z",
  },
];

const policies: Policy[] = [
  {
    id: 100,
    customer_id: 1,
    policy_type: "individual",
    premium_amount: "250.00",
    billing_cycle: "monthly",
    start_date: "2025-09-12",
    status: "active",
    grace_period_days: 30,
    lapse_threshold_months: 3,
    created_at: "2025-09-12T10:00:00Z",
    updated_at: "2025-09-12T10:00:00Z",
  },
  {
    id: 101,
    customer_id: 2,
    policy_type: "group_scheme",
    premium_amount: "850.00",
    billing_cycle: "monthly",
    start_date: "2025-10-04",
    status: "active",
    grace_period_days: 30,
    lapse_threshold_months: 3,
    created_at: "2025-10-04T08:30:00Z",
    updated_at: "2025-10-04T08:30:00Z",
  },
  {
    id: 102,
    customer_id: 3,
    policy_type: "individual",
    premium_amount: "180.00",
    billing_cycle: "monthly",
    start_date: "2025-08-21",
    status: "lapsed",
    grace_period_days: 30,
    lapse_threshold_months: 3,
    created_at: "2025-08-21T14:12:00Z",
    updated_at: "2026-03-01T09:00:00Z",
  },
  {
    id: 103,
    customer_id: 4,
    policy_type: "individual",
    premium_amount: "320.00",
    billing_cycle: "monthly",
    start_date: "2025-11-19",
    status: "active",
    grace_period_days: 30,
    lapse_threshold_months: 3,
    created_at: "2025-11-19T11:45:00Z",
    updated_at: "2025-11-19T11:45:00Z",
  },
];

const members: Member[] = [
  {
    id: 200,
    policy_id: 101,
    full_name: "Sipho Dlamini",
    id_number: "7806145122080",
    relationship_to_holder: "self",
    contribution_amount: "300.00",
    status: "active",
    created_at: "2025-10-04T08:30:00Z",
  },
  {
    id: 201,
    policy_id: 101,
    full_name: "Zanele Dlamini",
    id_number: null,
    relationship_to_holder: "spouse",
    contribution_amount: "250.00",
    status: "active",
    created_at: "2025-10-04T08:30:00Z",
  },
  {
    id: 202,
    policy_id: 101,
    full_name: "Lwazi Dlamini",
    id_number: null,
    relationship_to_holder: "child",
    contribution_amount: "150.00",
    status: "active",
    created_at: "2025-10-04T08:30:00Z",
  },
];

const payments: Payment[] = [
  { id: 300, customer_id: 1, policy_id: 100, member_id: null, amount_paid: "250.00", payment_date: "2026-03-01", payment_method: "debit_order", status: "paid", reference: "DO-MAR-001", created_at: "2026-03-01T08:00:00Z" },
  { id: 301, customer_id: 1, policy_id: 100, member_id: null, amount_paid: "250.00", payment_date: "2026-04-01", payment_method: "debit_order", status: "paid", reference: "DO-APR-001", created_at: "2026-04-01T08:00:00Z" },
  { id: 302, customer_id: 1, policy_id: 100, member_id: null, amount_paid: "250.00", payment_date: "2026-05-01", payment_method: "debit_order", status: "paid", reference: "DO-MAY-001", created_at: "2026-05-01T08:00:00Z" },
  { id: 310, customer_id: 2, policy_id: 101, member_id: null, amount_paid: "850.00", payment_date: "2026-04-01", payment_method: "eft", status: "paid", reference: "EFT-2026-04", created_at: "2026-04-01T10:00:00Z" },
  { id: 311, customer_id: 2, policy_id: 101, member_id: null, amount_paid: "850.00", payment_date: "2026-05-02", payment_method: "eft", status: "pending", reference: "EFT-2026-05", created_at: "2026-05-02T10:00:00Z" },
  { id: 320, customer_id: 4, policy_id: 103, member_id: null, amount_paid: "320.00", payment_date: "2026-04-05", payment_method: "cash", status: "paid", reference: "CASH-001", created_at: "2026-04-05T15:30:00Z" },
];

const notifications: NotificationItem[] = [
  { id: 400, customer_id: 3, policy_id: 102, type: "lapse_warning", message: "Policy in arrears for 2 months. Last payment 2026-02-21.", is_sent: true, sent_at: "2026-04-15T09:00:00Z", delivery_attempts: 1, last_error: null, created_at: "2026-04-15T09:00:00Z" },
  { id: 401, customer_id: 2, policy_id: 101, type: "payment_pending", message: "May 2026 EFT payment pending bank confirmation.", is_sent: false, sent_at: null, delivery_attempts: 0, last_error: null, created_at: "2026-05-02T10:05:00Z" },
  { id: 402, customer_id: 1, policy_id: 100, type: "payment_received", message: "May 2026 debit order received: R250.00.", is_sent: true, sent_at: "2026-05-01T08:05:00Z", delivery_attempts: 1, last_error: null, created_at: "2026-05-01T08:05:00Z" },
];

const auditLogs: AuditLogItem[] = [
  { id: 500, actor: "admin@example.com", action: "login", entity_type: "user", entity_id: "1", details: null, created_at: "2026-05-13T07:55:00Z" },
  { id: 501, actor: "admin@example.com", action: "create", entity_type: "customer", entity_id: "4", details: "Bongani Zulu", created_at: "2025-11-19T11:45:00Z" },
  { id: 502, actor: "admin@example.com", action: "create", entity_type: "policy", entity_id: "103", details: "individual / R320.00", created_at: "2025-11-19T11:45:30Z" },
  { id: 503, actor: "system", action: "lapse", entity_type: "policy", entity_id: "102", details: "auto-lapse after 3 months arrears", created_at: "2026-03-01T09:00:00Z" },
];

function buildCustomerStatus(customerId: number): CustomerPaymentStatusResponse {
  const pols = policies.filter((p) => p.customer_id === customerId);
  return {
    customer_id: customerId,
    overall_status: customers.find((c) => c.id === customerId)?.status === "lapsed" ? "OVERDUE" : "PAID",
    policies: pols.map((p) => ({
      policy_id: p.id,
      status: p.status,
      months_in_arrears: p.status === "lapsed" ? 3 : 0,
      total_outstanding: p.status === "lapsed" ? (Number(p.premium_amount) * 3).toFixed(2) : "0.00",
      months: ["2026-03", "2026-04", "2026-05"].map((m, i) => ({
        month: m,
        expected_amount: p.premium_amount,
        paid_amount: p.status === "lapsed" ? "0.00" : p.premium_amount,
        status: p.status === "lapsed" ? "OVERDUE" : (i === 2 ? "PAID" : "PAID"),
      })),
    })),
  };
}

function buildMembersStatus(policyId: number): MemberPaymentStatus[] {
  return members
    .filter((m) => m.policy_id === policyId)
    .map((m) => ({
      member_id: m.id,
      full_name: m.full_name,
      status: "PAID",
      months_in_arrears: 0,
      total_outstanding: "0.00",
    }));
}

function buildDashboard(): DashboardSummary {
  const active = customers.filter((c) => c.status === "active").length;
  const lapsed = customers.filter((c) => c.status === "lapsed").length;
  const cancelled = customers.filter((c) => c.status === "cancelled").length;
  const activePolicies = policies.filter((p) => p.status === "active").length;
  const lapsedPolicies = policies.filter((p) => p.status === "lapsed").length;
  const paidThisMonth = payments.filter((p) => p.status === "paid" && p.payment_date.startsWith("2026-05")).length;
  const pendingThisMonth = payments.filter((p) => p.status === "pending" && p.payment_date.startsWith("2026-05")).length;
  const revenue = payments
    .filter((p) => p.status === "paid" && p.payment_date.startsWith("2026-05"))
    .reduce((s, p) => s + Number(p.amount_paid), 0);
  const expected = policies.filter((p) => p.status === "active").reduce((s, p) => s + Number(p.premium_amount), 0);
  return {
    total_customers: customers.length,
    active_customers: active,
    lapsed_customers: lapsed,
    cancelled_customers: cancelled,
    total_policies: policies.length,
    active_policies: activePolicies,
    lapsed_policies: lapsedPolicies,
    paid_this_month: paidThisMonth,
    unpaid_this_month: pendingThisMonth,
    overdue_this_month: lapsedPolicies,
    revenue_this_month: revenue.toFixed(2),
    expected_revenue_this_month: expected.toFixed(2),
  };
}

function notFound(path: string): never {
  throw new ApiError(404, { detail: "Not found (demo)" }, `Not found: ${path}`);
}

export function mockRequest<T>(method: Method, path: string, body: any): Promise<T> {
  // Strip query string for matching.
  const [bare, query] = path.split("?");
  const qs = new URLSearchParams(query || "");

  // Auth
  if (method === "POST" && bare === "/auth/login") {
    return resolve({ access_token: "demo-token" });
  }
  if (method === "POST" && bare === "/auth/register") {
    return resolve(demoUser);
  }
  if (method === "GET" && bare === "/auth/me") {
    return resolve(demoUser);
  }

  // Customers
  if (method === "GET" && bare === "/customers") return resolve(customers);
  if (method === "POST" && bare === "/customers") {
    const c: Customer = {
      id: id(),
      full_name: body.full_name,
      id_number: body.id_number,
      phone: body.phone ?? null,
      email: body.email ?? null,
      status: "active",
      created_at: now(),
      updated_at: now(),
    };
    customers.push(c);
    return resolve(c);
  }
  const custMatch = bare.match(/^\/customers\/(\d+)(\/payment-status)?$/);
  if (custMatch) {
    const cid = Number(custMatch[1]);
    const c = customers.find((x) => x.id === cid);
    if (!c) return notFound(path);
    if (custMatch[2]) return resolve(buildCustomerStatus(cid));
    if (method === "GET") return resolve(c);
    if (method === "DELETE") {
      const idx = customers.indexOf(c);
      if (idx >= 0) customers.splice(idx, 1);
      return resolve(undefined as any);
    }
  }

  // Policies
  if (method === "POST" && bare === "/policies") {
    const p: Policy = {
      id: id(),
      customer_id: body.customer_id,
      policy_type: body.policy_type,
      premium_amount: body.premium_amount,
      billing_cycle: "monthly",
      start_date: body.start_date,
      status: "active",
      grace_period_days: body.grace_period_days ?? 30,
      lapse_threshold_months: body.lapse_threshold_months ?? 3,
      created_at: now(),
      updated_at: now(),
    };
    policies.push(p);
    return resolve(p);
  }
  const polMatch = bare.match(/^\/policies\/(\d+)$/);
  if (polMatch && method === "GET") {
    const p = policies.find((x) => x.id === Number(polMatch[1]));
    if (!p) return notFound(path);
    return resolve(p);
  }

  // Members
  const membersPolMatch = bare.match(/^\/members\/policy\/(\d+)(\/payment-status)?$/);
  if (membersPolMatch && method === "GET") {
    const pid = Number(membersPolMatch[1]);
    if (membersPolMatch[2]) return resolve(buildMembersStatus(pid));
    return resolve(members.filter((m) => m.policy_id === pid));
  }
  if (method === "POST" && bare === "/members") {
    const m: Member = {
      id: id(),
      policy_id: body.policy_id,
      full_name: body.full_name,
      id_number: body.id_number ?? null,
      relationship_to_holder: body.relationship_to_holder ?? null,
      contribution_amount: body.contribution_amount ?? null,
      status: "active",
      created_at: now(),
    };
    members.push(m);
    return resolve(m);
  }

  // Payments
  if (method === "GET" && bare === "/payments") {
    const cid = qs.get("customer_id");
    const list = cid ? payments.filter((p) => p.customer_id === Number(cid)) : payments;
    return resolve(list);
  }
  if (method === "POST" && bare === "/payments") {
    const p: Payment = {
      id: id(),
      customer_id: body.customer_id,
      policy_id: body.policy_id,
      member_id: body.member_id ?? null,
      amount_paid: body.amount_paid,
      payment_date: body.payment_date ?? today(),
      payment_method: body.payment_method,
      status: body.status ?? "paid",
      reference: body.reference ?? null,
      created_at: now(),
    };
    payments.push(p);
    return resolve(p);
  }

  // Dashboard / notifications / audit
  if (method === "GET" && bare === "/dashboard") return resolve(buildDashboard());
  if (method === "GET" && bare === "/notifications") return resolve(notifications);
  if (method === "GET" && bare === "/audit-logs") return resolve(auditLogs);

  return notFound(path);
}

function resolve<T>(value: any): Promise<T> {
  // Tiny artificial delay so loading states render briefly.
  return new Promise((r) => setTimeout(() => r(value as T), 80));
}
