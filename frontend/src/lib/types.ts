export type User = {
  id: string;
  email: string | null;
  display_name: string;
  currency: string;
  balance_cents: number | null;
  balance_as_of: string | null;
  safety_buffer_cents: number;
  is_demo: boolean;
  expires_at: string | null;
};

export type Totals = { income_cents: number; spending_cents: number; net_cents: number };
export type Severity = "alert" | "watch" | "info" | "good";

export type Insight = {
  key: string;
  kind: string;
  severity: Severity;
  title: string;
  detail: string;
  monthly_impact_cents: number;
  txn_ids: string[];
  action: string | null;
};

export type ForecastPoint = { date: string; balance_cents: number; low_cents: number; high_cents: number };

export type SafeToSpend = {
  amount_cents: number;
  shortfall_cents: number;
  per_day_cents: number;
  days: number;
  until: string;
  until_kind: "payday" | "month_end";
  usual_per_day_cents: number;
  breakdown: {
    balance_cents: number;
    bills_cents: number;
    buffer_cents: number;
    goals_cents: number;
    held_back_cents: number;
  };
};

export type UpcomingEvent = { merchant: string; category: string; amount_cents: number; date: string };

export type Forecast = {
  latest_data_date: string | null;
  stale_days: number;
  needs_balance: boolean;
  daily_variable_cents: number;
  upcoming: UpcomingEvent[];
  points: ForecastPoint[];
  low_point: { date: string; balance_cents: number } | null;
  month_end_balance_cents: number | null;
  safe_to_spend: SafeToSpend | null;
};

export type BudgetRow = {
  category: string;
  limit_cents: number;
  spent_cents: number;
  remaining_cents: number;
  projected_cents: number;
  percent_used: number;
  status: "ok" | "watch" | "over";
};

export type Overview = {
  today: string;
  has_data: boolean;
  balance_cents: number | null;
  this_month: Totals;
  last_month: Totals;
  average: Totals & { months: number };
  series: ({ month: string } & Totals)[];
  categories: { name: string; amount_cents: number; count: number }[];
  last_month_categories: { name: string; amount_cents: number; count: number }[];
  top_merchants: { name: string; amount_cents: number; count: number }[];
  forecast: Forecast;
  insights: Insight[];
  budgets: BudgetRow[];
};

export type Txn = {
  id: string;
  date: string;
  amount_cents: number;
  merchant: string;
  raw_description: string;
  category: string;
  category_source: string;
};

export type Suggestion = {
  category: string;
  limit_cents: number;
  typical_cents: number;
  lowest_cents: number;
  highest_cents: number;
  saving_cents: number;
  kind: "fixed" | "flexible" | "occasional";
  reason: string;
};

export type Stream = {
  merchant: string;
  category: string;
  direction: "out" | "in";
  cadence: string;
  amount_cents: number;
  monthly_cents: number;
  next_date: string;
  active: boolean;
  is_subscription: boolean;
  price_change_cents: number;
};

export type GoalPlan = {
  id: string;
  name: string;
  target_cents: number;
  saved_cents: number;
  remaining_cents: number;
  percent: number;
  target_date: string | null;
  months_left: number | null;
  required_monthly_cents: number;
  allocated_monthly_cents: number;
  projected_date: string | null;
  status: "done" | "on_track" | "tight" | "behind" | "open" | "paused";
  cuts: { category: string; cut_cents: number }[];
  gap_monthly_cents?: number;
};

export type Goals = {
  monthly_surplus_cents: number;
  unallocated_monthly_cents: number;
  plans: GoalPlan[];
};

export type ChartSpec =
  | { kind: "bars"; title: string; rows: { label: string; value_cents: number }[] }
  | { kind: "forecast"; title: string; rows: ForecastPoint[] }
  | {
      kind: "budget";
      title: string;
      rows: { label: string; spent_cents: number; limit_cents: number; status: BudgetRow["status"] }[];
    }
  | { kind: "scenario"; title: string; rows: { label: string; baseline_cents: number; scenario_cents: number }[] }
  | { kind: "goals"; title: string; rows: { label: string; saved_cents: number; target_cents: number; status: string }[] }
  | { kind: "cashflow"; title: string; rows: { label: string; income_cents: number; spending_cents: number }[] };

export type Evidence = {
  label: string;
  total: number;
  href: string;
  items: { id: string; date: string; merchant: string; category: string; amount_cents: number }[];
};

export type ChatMeta = {
  mode?: "local_ai" | "built_in";
  verified?: boolean;
  tools_used?: string[];
  charts?: ChartSpec[];
  evidence?: Evidence[];
  suggestions?: string[];
  note?: string | null;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  meta: ChatMeta;
  created_at: string;
};

export type SimulationResult = {
  baseline: Totals;
  scenario: Totals;
  monthly_delta_cents: number;
  yearly_delta_cents: number;
  impacts: { label: string; monthly_cents: number; base_monthly_cents: number; one_off_cents?: number }[];
  series: { month: string; baseline_cents: number; scenario_cents: number }[];
  warnings: string[];
  has_balance: boolean;
};

export type AffordResult = {
  verdict: "yes" | "yes_with_savings" | "with_cuts" | "not_yet";
  amount_cents: number;
  by: string;
  months: number;
  monthly_surplus_cents: number;
  surplus_by_date_cents: number;
  spare_balance_cents: number;
  required_monthly_cents: number;
  gap_cents: number;
  gap_monthly_cents: number;
  suggested_cuts: { category: string; cut_cents: number }[];
  earliest_date: string | null;
  has_balance: boolean;
};

export type ImportPreview = {
  filename: string;
  source_type: string;
  rows: number;
  failed_rows: number;
  duplicates: number;
  uncategorized: number;
  first_date: string;
  last_date: string;
  date_order: string;
  date_order_ambiguous: boolean;
  amounts_look_reversed: boolean;
  warnings: string[];
  sample: { date: string; description: string; merchant: string; category: string; amount_cents: number }[];
};

export type ImportBatch = {
  id: string;
  filename: string;
  source_type: string;
  rows_imported: number;
  rows_duplicate: number;
  rows_failed: number;
  created_at: string;
};
