"use client";

import { AlertTriangle, CheckCircle2, Eye, Info, type LucideIcon, TrendingDown } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { send } from "@/lib/api";
import type { BudgetRow, Insight, Severity } from "@/lib/types";
import { useMoney } from "./UserContext";

const SEVERITY: Record<Severity, { icon: LucideIcon; label: string }> = {
  alert: { icon: AlertTriangle, label: "Needs attention" },
  watch: { icon: Eye, label: "Worth a look" },
  info: { icon: Info, label: "Good to know" },
  good: { icon: TrendingDown, label: "Going well" },
};

function insightHref(insight: Insight): string | null {
  if (insight.kind === "low_balance") return "/plan";
  if (insight.kind === "goal") return "/goals";
  if (insight.kind === "budget") return "/budgets";
  if (insight.txn_ids.length) return `/transactions?ids=${insight.txn_ids.slice(0, 30).join(",")}`;
  return null;
}

export function InsightItem({ insight, onDismiss }: { insight: Insight; onDismiss?: () => void }) {
  const { icon: Icon, label } = SEVERITY[insight.severity];
  const href = insightHref(insight);

  async function dismiss() {
    await send(`/api/insights/${encodeURIComponent(insight.key)}/dismiss`, "POST");
    onDismiss?.();
  }

  return (
    <li className="insight">
      <Icon size={18} className={`tone-${insight.severity}`} aria-label={label} role="img" />
      <span className="insight-title">{insight.title}</span>
      <span />
      <span className="insight-detail">{insight.detail}</span>
      <span className="insight-links">
        {href && <Link href={href}>{insight.txn_ids.length ? `See ${insight.txn_ids.length === 1 ? "the charge" : "the transactions"}` : (insight.action ?? "Open")}</Link>}
        {onDismiss && (
          <button className="dismiss" onClick={dismiss}>
            Dismiss
          </button>
        )}
      </span>
    </li>
  );
}

const BUDGET_STATUS = {
  ok: { icon: CheckCircle2, label: "On track", tone: "tone-good" },
  watch: { icon: Eye, label: "Heading over", tone: "tone-watch" },
  over: { icon: AlertTriangle, label: "Over budget", tone: "tone-alert" },
} as const;

export function BudgetStatusLabel({ status }: { status: BudgetRow["status"] }) {
  const { icon: Icon, label, tone } = BUDGET_STATUS[status];
  return (
    <span className={`status ${tone}`}>
      <Icon size={15} aria-hidden="true" />
      {label}
    </span>
  );
}

export function BudgetMeter({ row, dayFraction }: { row: BudgetRow; dayFraction?: number }) {
  const money = useMoney();
  const width = Math.min((row.spent_cents / Math.max(row.limit_cents, 1)) * 100, 100);
  return (
    <div className="bar-row">
      <div className="bar-labels">
        <span>
          <strong>{row.category}</strong> <BudgetStatusLabel status={row.status} />
        </span>
        <span>
          {money(row.spent_cents, true)} of {money(row.limit_cents, true)}
        </span>
      </div>
      <div
        className="bar-track"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={row.limit_cents}
        aria-valuenow={Math.min(row.spent_cents, row.limit_cents)}
        aria-label={`${row.category}: ${money(row.spent_cents)} spent of ${money(row.limit_cents)}`}
      >
        <div className={`bar-fill ${row.status === "over" ? "over" : ""}`} style={{ width: `${width}%` }} />
        {dayFraction !== undefined && <div className="bar-mark" style={{ left: `${dayFraction * 100}%` }} title="Today" />}
      </div>
    </div>
  );
}

export function PageError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="form-error" role="alert">
      {message}{" "}
      {onRetry && (
        <button className="link-btn" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function Toast({ message, onDone }: { message: string | null; onDone: () => void }) {
  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(onDone, 4000);
    return () => clearTimeout(timer);
  }, [message, onDone]);
  if (!message) return null;
  return (
    <div className="toast" role="status">
      {message}
    </div>
  );
}

export function PasswordField({
  label,
  value,
  onChange,
  autoComplete,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: string;
  hint?: string;
}) {
  const [show, setShow] = useState(false);
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        className="input"
        type={show ? "text" : "password"}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoComplete={autoComplete}
        required
      />
      <span className="row" style={{ justifyContent: "space-between" }}>
        <span className="hint">{hint}</span>
        <button type="button" className="link-btn small" onClick={() => setShow(!show)}>
          {show ? "Hide password" : "Show password"}
        </button>
      </span>
    </div>
  );
}
