export interface FieldDevice {
  device_id: number;
  name: string;
  jwt: string;
  enrolled_at: string;
}

export interface FieldCoverPlan {
  id: number;
  category: string;
  cover_type: string;
  monthly_premium: string;
  max_dependents: number;
  description: string | null;
}

export interface FieldPerson {
  title: string;
  first_names: string;
  surname: string;
  id_number?: string;
  relationship_to_holder?: string;
  gender?: string;
  date_of_birth?: string;
  nationality?: string;
  email?: string;
  cellphone?: string;
  country_of_birth?: string;
}

export interface FieldBeneficiary {
  relationship_to_holder: string;
  title?: string;
  first_name: string;
  surname: string;
  gender?: string;
  date_of_birth?: string;
  nationality?: string;
  email?: string;
  cellphone?: string;
  country_of_birth?: string;
  share_pct: string;
}

export interface FieldSignupDraft {
  client_uuid: string;
  local_id: string;
  cover_plan_id: number | "";
  holder: FieldPerson;
  photo_data_url?: string;
  id_photo_id?: string;
  dependents: FieldPerson[];
  beneficiaries: FieldBeneficiary[];
  first_payment_enabled: boolean;
  first_payment: {
    amount: string;
    method: "cash" | "eft" | "debit_order";
    reference: string;
  };
  email_receipt_requested: boolean;
  updated_at: string;
}

export interface FieldSubmissionPayload {
  client_uuid: string;
  signups: Array<{
    local_id: string;
    cover_plan_id: number;
    holder: Record<string, string | null>;
    id_photo_id?: string;
    dependents: Array<Record<string, string | null>>;
    beneficiaries: Array<Record<string, string | null>>;
    first_payment?: {
      amount: string;
      method: string;
      reference?: string | null;
    };
    email_receipt_requested: boolean;
  }>;
}

export interface FieldSubmissionResult {
  local_id: string;
  status: "ok" | "error";
  customer_id?: number | null;
  policy_id?: number | null;
  payment_id?: number | null;
  error?: string | null;
}

export interface FieldSubmissionResponse {
  field_submission_id: number;
  results: FieldSubmissionResult[];
}

export interface FieldPendingSubmission {
  client_uuid: string;
  payload: FieldSubmissionPayload;
  photo_data_url?: string;
  status: "queued" | "syncing" | "synced" | "failed";
  attempts: number;
  created_at: string;
  updated_at: string;
  last_error?: string;
  server_result?: FieldSubmissionResponse;
}
