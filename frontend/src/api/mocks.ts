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
  full_name: null,
  is_admin: true,
  role: "admin",
};

const customers: Customer[] = [];
const policies: Policy[] = [];
const members: Member[] = [];
const payments: Payment[] = [];
const notifications: NotificationItem[] = [];
const auditLogs: AuditLogItem[] = [];

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
