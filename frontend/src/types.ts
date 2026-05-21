// Type definitions matching the FastAPI response schemas.
export type CustomerStatus = "active" | "lapsed" | "cancelled";
export type PolicyStatus = "active" | "lapsed" | "cancelled";
export type PolicyType = "individual" | "group_scheme";
export type PaymentMethod = "debit_order" | "cash" | "eft";
export type PaymentStatusValue = "paid" | "pending" | "failed";

export type Role = "admin" | "agent" | "viewer";

export interface User {
  id: number;
  email: string;
  full_name: string | null;
  is_admin: boolean;
  role: Role;
}

export interface Customer {
  id: number;
  full_name: string;
  id_number: string;
  phone: string | null;
  email: string | null;
  status: CustomerStatus;
  created_at: string;
  updated_at: string;
}

export interface Policy {
  id: number;
  customer_id: number;
  policy_type: PolicyType;
  premium_amount: string;
  billing_cycle: "monthly";
  start_date: string;
  status: PolicyStatus;
  grace_period_days: number | null;
  lapse_threshold_months: number | null;
  created_at: string;
  updated_at: string;
}

export interface Payment {
  id: number;
  customer_id: number;
  policy_id: number;
  member_id: number | null;
  amount_paid: string;
  payment_date: string;
  payment_method: PaymentMethod;
  status: PaymentStatusValue;
  reference: string | null;
  created_at: string;
}

export interface Member {
  id: number;
  policy_id: number;
  full_name: string;
  id_number: string | null;
  relationship_to_holder: string | null;
  contribution_amount: string | null;
  status: "active" | "lapsed" | "removed";
  created_at: string;
}

export type MonthStatus = "PAID" | "NOT_PAID" | "OVERDUE" | "PARTIAL";

export interface MonthPaymentStatus {
  month: string;
  expected_amount: string;
  paid_amount: string;
  status: MonthStatus;
}

export interface PolicyPaymentStatus {
  policy_id: number;
  status: PolicyStatus;
  months_in_arrears: number;
  total_outstanding: string;
  months: MonthPaymentStatus[];
}

export interface CustomerPaymentStatusResponse {
  customer_id: number;
  overall_status: "PAID" | "NOT_PAID" | "OVERDUE";
  policies: PolicyPaymentStatus[];
}

export interface MemberPaymentStatus {
  member_id: number;
  full_name: string;
  status: MonthStatus;
  months_in_arrears: number;
  total_outstanding: string;
}

export interface DashboardSummary {
  total_customers: number;
  active_customers: number;
  lapsed_customers: number;
  cancelled_customers: number;
  total_policies: number;
  active_policies: number;
  lapsed_policies: number;
  paid_this_month: number;
  unpaid_this_month: number;
  overdue_this_month: number;
  revenue_this_month: string;
  expected_revenue_this_month: string;
}

export interface NotificationItem {
  id: number;
  customer_id: number;
  policy_id: number | null;
  type: string;
  message: string;
  is_sent: boolean;
  sent_at: string | null;
  delivery_attempts: number;
  last_error: string | null;
  created_at: string;
}

export interface AuditLogItem {
  id: number;
  actor: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  details: string | null;
  created_at: string;
}

// Mirrors app/models/cover_plan.py SchemeType
export type SchemeType =
  | "funeral"
  | "stokvel"
  | "purchase"
  | "goat_purchase"
  | "wedding"
  | "party"
  | "breeding"
  | "farming";

export interface SchemeManifestEntry {
  type: SchemeType;
  label: string;
  status: "active" | "coming_soon";
}

// Single source of truth for the sidebar and routing.
export const SCHEME_MANIFEST: readonly SchemeManifestEntry[] = [
  { type: "funeral",       label: "Funeral",       status: "active" },
  { type: "stokvel",       label: "Stokvel",       status: "active" },
  { type: "purchase",      label: "Purchase",      status: "active" },
  { type: "goat_purchase", label: "Goat purchase", status: "active" },
  { type: "wedding",       label: "Wedding",       status: "coming_soon" },
  { type: "party",         label: "Party",         status: "coming_soon" },
  { type: "breeding",      label: "Breeding",      status: "coming_soon" },
  { type: "farming",       label: "Farming",       status: "coming_soon" },
] as const;

export interface SchemeOverviewResponse {
  scheme_type: SchemeType;
  label: string;
  active_customers: number;
  lapsed_customers: number;
  active_policies: number;
  lapsed_policies: number;
  paid_this_month: number;
  unpaid_this_month: number;
  overdue_this_month: number;
  revenue_this_month: string;
  expected_revenue_this_month: string;
  plan_count: number;
}
