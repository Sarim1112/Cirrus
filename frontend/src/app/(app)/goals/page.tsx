"use client";

import { AlertTriangle, CheckCircle2, CircleDashed, Eye, type LucideIcon, PartyPopper } from "lucide-react";
import { useCallback, useState } from "react";
import { PageError, Toast } from "@/components/ui";
import { useMoney } from "@/components/UserContext";
import { send, useFetch } from "@/lib/api";
import { monthYear, parseDollars } from "@/lib/format";
import type { GoalPlan, Goals } from "@/lib/types";

const STATUS: Record<GoalPlan["status"], { label: string; icon: LucideIcon; tone: string }> = {
  done: { label: "Reached", icon: PartyPopper, tone: "tone-good" },
  on_track: { label: "On track", icon: CheckCircle2, tone: "tone-good" },
  tight: { label: "A little tight", icon: Eye, tone: "tone-watch" },
  behind: { label: "Behind", icon: AlertTriangle, tone: "tone-alert" },
  open: { label: "In progress", icon: CircleDashed, tone: "tone-info" },
  paused: { label: "Paused: no surplus right now", icon: CircleDashed, tone: "tone-watch" },
};

function GoalRow({ plan, reload, say }: { plan: GoalPlan; reload: () => void; say: (message: string) => void }) {
  const money = useMoney();
  const [adding, setAdding] = useState("");
  const [failure, setFailure] = useState<string | null>(null);
  const { label, icon: Icon, tone } = STATUS[plan.status];

  async function add(event: React.FormEvent) {
    event.preventDefault();
    const cents = parseDollars(adding);
    if (cents === null || cents <= 0) {
      setFailure("Enter a dollar amount above zero.");
      return;
    }
    try {
      await send(`/api/goals/${plan.id}`, "PATCH", { saved_cents: plan.saved_cents + cents });
      setAdding("");
      setFailure(null);
      say(`Added ${money(cents)} to ${plan.name}.`);
      reload();
    } catch (caught) {
      setFailure((caught as Error).message);
    }
  }

  async function remove() {
    await send(`/api/goals/${plan.id}`, "DELETE");
    say(`Deleted ${plan.name}.`);
    reload();
  }

  return (
    <li className="stack" style={{ gap: 9 }}>
      <div className="bar-labels">
        <h3 style={{ fontSize: "1.2rem" }}>{plan.name}</h3>
        <span className={`status ${tone}`}>
          <Icon size={15} aria-hidden="true" />
          {label}
        </span>
      </div>
      <div className="bar-labels">
        <span>
          {money(plan.saved_cents, true)} of {money(plan.target_cents, true)}
        </span>
        <span className="muted">{plan.target_date ? `by ${monthYear(plan.target_date)}` : "No deadline"}</span>
      </div>
      <div className="bar-track" role="progressbar" aria-valuenow={plan.percent} aria-valuemin={0} aria-valuemax={100} aria-label={`${plan.name} progress`}>
        <div className="bar-fill" style={{ width: `${plan.percent}%` }} />
      </div>
      {plan.status !== "done" && (
        <p className="small">
          {plan.target_date ? `This takes ${money(plan.required_monthly_cents)} a month. ` : ""}
          Your surplus can put {money(plan.allocated_monthly_cents, true)} a month toward it
          {plan.projected_date ? `, finishing around ${monthYear(plan.projected_date)}` : ""}.
        </p>
      )}
      {plan.cuts.length > 0 && (
        <p className="small muted">
          To close the gap, trim {plan.cuts.map((cut) => `${cut.category} by ${money(cut.cut_cents, true)}`).join(" and ")} a month.
        </p>
      )}
      <form className="row" onSubmit={add}>
        <label>
          <span className="sr-only">Amount to add to {plan.name}</span>
          <input className="input" style={{ width: 120 }} inputMode="decimal" placeholder="Amount" value={adding} onChange={(event) => setAdding(event.target.value)} />
        </label>
        <button className="btn quiet" type="submit">
          Add savings
        </button>
        <button className="link-btn small" type="button" onClick={remove}>
          Delete goal
        </button>
      </form>
      {failure && <PageError message={failure} />}
    </li>
  );
}

export default function GoalsPage() {
  const money = useMoney();
  const { data, error, reload } = useFetch<Goals>("/api/goals");
  const [name, setName] = useState("");
  const [target, setTarget] = useState("");
  const [saved, setSaved] = useState("");
  const [date, setDate] = useState("");
  const [failure, setFailure] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const clearToast = useCallback(() => setToast(null), []);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    const targetCents = parseDollars(target);
    const savedCents = saved ? parseDollars(saved) : 0;
    if (targetCents === null || targetCents <= 0) {
      setFailure("Enter a target amount above zero.");
      return;
    }
    if (savedCents === null || savedCents < 0) {
      setFailure("Enter the amount you've already saved, or leave it empty.");
      return;
    }
    try {
      await send("/api/goals", "POST", { name, target_cents: targetCents, saved_cents: savedCents, target_date: date || null });
      setName("");
      setTarget("");
      setSaved("");
      setDate("");
      setFailure(null);
      setToast(`Added ${name}.`);
      await reload();
    } catch (caught) {
      setFailure((caught as Error).message);
    }
  }

  return (
    <div className="page stack" style={{ gap: 32 }}>
      <div className="page-head" style={{ marginBottom: 0 }}>
        <div>
          <h1>Goals</h1>
          <p className="muted">Plans update on their own as your spending changes, with the earliest deadline funded first.</p>
        </div>
        {data && (
          <div>
            <div className="stat-label">Free each month</div>
            <div className="stat-value">{money(data.monthly_surplus_cents, true)}</div>
          </div>
        )}
      </div>
      {error && <PageError message={error} onRetry={reload} />}

      {data && data.plans.length > 0 && (
        <ul className="rule-list">
          {data.plans.map((plan) => (
            <GoalRow key={plan.id} plan={plan} reload={reload} say={setToast} />
          ))}
        </ul>
      )}

      <section className="panel stack" aria-labelledby="new-goal">
        <h2 id="new-goal">Add a goal</h2>
        <form className="grid-form" onSubmit={create}>
          <label className="field">
            Name
            <input className="input" required maxLength={80} placeholder="Lisbon trip" value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label className="field">
            Target
            <input className="input" required inputMode="decimal" placeholder="1500" value={target} onChange={(event) => setTarget(event.target.value)} />
          </label>
          <label className="field">
            Saved so far
            <input className="input" inputMode="decimal" placeholder="0" value={saved} onChange={(event) => setSaved(event.target.value)} />
          </label>
          <label className="field">
            Target date
            <input className="input" type="date" value={date} onChange={(event) => setDate(event.target.value)} />
          </label>
          <button className="btn" type="submit">
            Add goal
          </button>
        </form>
        {failure && <PageError message={failure} />}
      </section>
      <Toast message={toast} onDone={clearToast} />
    </div>
  );
}
