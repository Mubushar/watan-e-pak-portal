/** Responses of the CRM intelligence endpoints (backend crm_ai.py / crm_channels.py). */

export interface PriorityLead {
  id: string;
  name: string;
  phone?: string | null;
  email?: string | null;
  status: string;
  score: number;
  temperature: "hot" | "warm" | "cold";
  city?: string | null;
  budget_max?: number | null;
  agent?: string | null;
  last_contact_days: number | null;
  priority: number;
  action: string;
  channel: string;
  urgency: "urgent" | "high" | "medium" | "low";
}

export interface AgendaTask {
  id: string;
  title: string;
  due_date?: string | null;
  priority: string;
  status: string;
  related_type?: string | null;
  related_id?: string | null;
  agent?: string | null;
  overdue: boolean;
}

export interface ChannelStatus {
  email: { live: boolean; provider: string; setup: string };
  sms: { live: boolean; provider: string; setup: string };
  whatsapp: { live: boolean; provider: string; template?: string | null; setup: string };
  inbound: { lead_webhook: string; lead_webhook_secured: boolean; whatsapp_webhook: string; whatsapp_verify_token_set: boolean };
  ai?: boolean;
  voice?: boolean;
}

export interface CrmInsights {
  period_days: number;
  generated_at: string;
  ai: boolean;
  kpis: {
    leads_total: number;
    leads_new: number;
    leads_open: number;
    leads_hot: number;
    leads_uncontacted: number;
    conversion_rate: number | null;
    avg_first_response_hours: number | null;
    pipeline_open: number;
    pipeline_weighted: number;
    won_value: number;
    won_count: number;
    avg_deal_size: number | null;
    commission_won: number;
    tasks_open: number;
    tasks_overdue: number;
    tasks_due_today: number;
    appointments_week: number;
    interactions_period: number;
  };
  trend: { date: string; leads: number; touches: number; won: number }[];
  by_source: { source: string; count: number }[];
  by_status: { status: string; count: number }[];
  by_city: { city: string; count: number }[];
  channel_mix: { channel: string; count: number }[];
  funnel: { stage: string; count: number }[];
  pipeline: { stage: string; count: number; value: number }[];
  agents: {
    agent_id: string;
    name: string;
    active: boolean;
    rating: number;
    leads: number;
    contacted_pct: number | null;
    hot: number;
    won_count: number;
    won_value: number;
    pipeline: number;
    commission: number;
    overdue_tasks: number;
  }[];
  priority_leads: PriorityLead[];
  at_risk_deals: { id: string; title: string; stage: string; amount: number; probability: number; agent?: string | null; reasons: string[] }[];
  agenda: {
    overdue: AgendaTask[];
    today: AgendaTask[];
    appointments: { id: string; title: string; scheduled_at: string; agent?: string | null; lead_id?: string | null; property_id?: string | null }[];
  };
  channels: ChannelStatus;
}

export interface LeadBrief {
  lead_id: string;
  name: string;
  source: "ai" | "rules";
  lang: string;
  temperature: string;
  score: number;
  summary: string;
  next_best_action: string;
  channel: string;
  urgency: string;
  follow_up_date: string;
  talking_points: string[];
  risks: string[];
  drafts: { whatsapp: string; sms: string; email_subject: string; email_body: string };
  goal: string;
  matches: { id: string; title: string; price: number }[];
}

export interface Draft {
  channel: string;
  goal: string;
  lang: string;
  subject: string | null;
  body: string;
  source: "ai" | "rules";
}

export interface NoteResult {
  transcript: string;
  analysis: {
    summary: string;
    sentiment: string;
    intent?: string;
    budget_pkr?: number | null;
    timeline?: string;
    next_step?: string | null;
    follow_up_date?: string | null;
    status_suggestion?: string | null;
    tasks: { title: string; due_date?: string | null; priority?: string }[];
    source: "ai" | "rules";
  };
  applied: { interaction: unknown; tasks: unknown[]; updated: Record<string, unknown> } | null;
}

export interface AskResult {
  answer: string;
  lead_ids: string[];
  source: "ai" | "rules";
  question: string;
  transcript?: string | null;
  audio_base64?: string;
  mime_type?: string;
}

export interface SendResult {
  status: "sent" | "simulated" | "failed";
  provider: string | null;
  error: string | null;
  to: string;
}

export const GOALS: { value: string; label: string }[] = [
  { value: "follow_up", label: "Follow up" },
  { value: "new_matches", label: "Share new matches" },
  { value: "site_visit", label: "Invite to site visit" },
  { value: "price_update", label: "Price / plan update" },
  { value: "proposal", label: "Send proposal" },
  { value: "re_engage", label: "Re-engage (gone quiet)" },
  { value: "thank_you", label: "Thank you" },
];
