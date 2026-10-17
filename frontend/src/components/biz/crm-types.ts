/** CRM payload shapes (observed on the live API). */

export const LEAD_STATUSES = ["new", "contacted", "qualified", "proposal", "negotiation", "won", "lost"] as const;
export const DEAL_STAGES = ["prospecting", "qualification", "proposal", "negotiation", "contract", "closed_won", "closed_lost"] as const;
export const TASK_PRIORITIES = ["low", "medium", "high", "urgent"] as const;
export const LEAD_SOURCES = ["website", "referral", "walk_in", "call", "whatsapp", "portal", "social", "email", "sms"] as const;
export const CUSTOMER_TYPES = ["buyer", "seller", "tenant", "landlord", "investor"] as const;
export const INTERACTION_CHANNELS = ["call", "email", "meeting", "whatsapp", "site_visit", "sms"] as const;

export interface Lead {
  id: string;
  name: string;
  email?: string | null;
  phone?: string | null;
  source: string;
  status: string;
  score: number;
  interest_use_type?: string | null;
  interest_category?: string | null;
  budget_min?: number | null;
  budget_max?: number | null;
  city_id?: string | null;
  scheme_id?: string | null;
  assigned_agent_id?: string | null;
  notes?: string | null;
  converted_customer_id?: string | null;
  created_at: string;
  updated_at?: string;
  city_name?: string | null;
  agent_name?: string | null;
}

export interface Agent {
  id: string;
  name: string;
  email?: string | null;
  phone?: string | null;
  region?: string | null;
  specialization?: string | null;
  active: boolean;
  rating: number;
  deals_closed: number;
  commission_rate: number;
}

export interface Deal {
  id: string;
  title: string;
  lead_id?: string | null;
  customer_id?: string | null;
  property_id?: string | null;
  agent_id?: string | null;
  amount: number;
  currency?: string;
  stage: string;
  probability: number;
  commission?: number;
  expected_close_date?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface Customer {
  id: string;
  name: string;
  email?: string | null;
  phone?: string | null;
  type: string;
  assigned_agent_id?: string | null;
  source_lead_id?: string | null;
  notes?: string | null;
  created_at: string;
}

export interface Task {
  id: string;
  title: string;
  description?: string | null;
  assigned_agent_id?: string | null;
  related_type?: string | null;
  related_id?: string | null;
  due_date?: string | null;
  priority: string;
  status: string;
  created_at: string;
}

export interface Appointment {
  id: string;
  title: string;
  lead_id?: string | null;
  customer_id?: string | null;
  property_id?: string | null;
  agent_id?: string | null;
  scheduled_at: string;
  status: string;
  notes?: string | null;
}

export interface Interaction {
  id: string;
  entity_type: string;
  entity_id: string;
  channel: string;
  direction: string;
  summary: string;
  agent_id?: string | null;
  occurred_at: string;
}

export interface Pipeline {
  stages: Record<string, { count: number; value: number; weighted: number }>;
  open_pipeline_value: number;
  won_value: number;
  total_deals: number;
}

export type LeadsRes = { count: number; leads: Lead[] };
export type AgentsRes = { count: number; agents: Agent[] };
export type DealsRes = { count: number; deals: Deal[] };
