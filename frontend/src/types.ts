export type QueueCase = {
  claim_id: string;
  status: string;
  summary?: string | null;
  waiting_on_adjuster: boolean;
  n_conflicts: number;
  updated_at?: string | null;
};

export type FieldRow = {
  name: string;
  ai_value: string | null;
  citation: string | null;
  document_id: string | null;
  corrected_value: string | null;
  effective_value: string | null;
};

export type Enriched = {
  case: Record<string, unknown>;
  audit: Array<{ component?: string; action?: string; created_at?: string; output?: unknown }>;
  review: {
    phase: string;
    phase_label: string;
    waiting_on_adjuster: boolean;
    can_approve_send: boolean;
    can_reject: boolean;
    instruction?: string;
    fields: FieldRow[];
    documents: Array<Record<string, unknown>>;
    conflicts: Array<Record<string, unknown>>;
    policy_checks: Array<Record<string, unknown>>;
    draft: string | null;
    summary?: string | null;
    execution_arn?: string | null;
    outbound_message_id?: string | null;
  };
};

export type Flash = { kind: "ok" | "err"; text: string } | null;

export const FIELD_META: Record<string, { label: string; help: string }> = {
  claimId: {
    label: "Claim ID",
    help: "Correct only if the ID on the FNOL/email does not match this case.",
  },
  policyId: {
    label: "Policy number",
    help: "Must match the policy document. Fix typos or OCR misses.",
  },
  dateOfLoss: {
    label: "Date of loss",
    help: "Incident / loss date from the claim form or notice.",
  },
  dateOfReported: {
    label: "Date reported",
    help: "When the insured reported the claim (often later than loss date).",
  },
  lossEvent: {
    label: "Loss event",
    help: "Short description of what happened (water damage, fire, theft, etc.).",
  },
  claimant: {
    label: "Claimant / insured",
    help: "Person or household named on the claim.",
  },
  product: {
    label: "Product / cover",
    help: "Policy product line if stated (e.g. home contents).",
  },
};
