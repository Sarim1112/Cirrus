"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ForecastChart, ScenarioChart } from "@/components/charts";
import { PageError } from "@/components/ui";
import { useMoney } from "@/components/UserContext";
import { send, useFetch } from "@/lib/api";
import { longDate, monthYear, parseDollars, shortDate } from "@/lib/format";
import type { AffordResult, Forecast, SimulationResult, Stream, Suggestion } from "@/lib/types";

type Recurring = { streams: Stream[]; subscriptions_monthly_cents: number; bills_monthly_cents: number };

function Simulator({ suggestions, streams }: { suggestions: Suggestion[]; streams: Stream[] }) {
  const money = useMoney();
  const flexible = useMemo(() => suggestions.filter((row) => row.kind !== "fixed").slice(0, 5), [suggestions]);
  const subscriptions = useMemo(() => streams.filter((row) => row.is_subscription && row.active), [streams]);
  const [cuts, setCuts] = useState<Record<string, number>>({});
  const [cancelled, setCancelled] = useState<Record<string, boolean>>({});
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    const changes = [
      ...Object.entries(cuts)
        .filter(([, percent]) => percent > 0)
        .map(([category, percent]) => ({ type: "cut_category", category, percent })),
      ...Object.entries(cancelled)
        .filter(([, on]) => on)
        .map(([merchant]) => ({ type: "cancel_merchant", merchant })),
    ];
    if (!changes.length) {
      const reset = setTimeout(() => setResult(null), 0);
      return () => clearTimeout(reset);
    }
    const timer = setTimeout(() => {
      send<SimulationResult>("/api/simulate", "POST", { changes })
        .then((value) => {
          setResult(value);
          setFailure(null);
        })
        .catch((caught: Error) => setFailure(caught.message));
    }, 200);
    return () => clearTimeout(timer);
  }, [cuts, cancelled]);

  return (
    <section className="section" aria-labelledby="whatif">
      <h2 id="whatif">What if</h2>
      <div className="split">
        <div className="stack">
          {flexible.map((row) => (
            <label className="field" key={row.category}>
              <span className="bar-labels" style={{ fontWeight: 600 }}>
                <span>{row.category}</span>
                <span>{cuts[row.category] ? `${cuts[row.category]}% less` : "No change"}</span>
              </span>
              <input
                type="range"
                min={0}
                max={100}
                step={5}
                value={cuts[row.category] ?? 0}
                onChange={(event) => setCuts({ ...cuts, [row.category]: Number(event.target.value) })}
              />
            </label>
          ))}
          {subscriptions.length > 0 && (
            <fieldset style={{ border: 0, padding: 0, margin: 0 }} className="stack">
              <legend style={{ fontWeight: 600, marginBottom: 8 }}>Cancel a subscription</legend>
              <div className="chips">
                {subscriptions.map((row) => (
                  <label className="chip" key={row.merchant} style={{ display: "inline-flex", gap: 7, alignItems: "center" }}>
                    <input
                      type="checkbox"
                      checked={Boolean(cancelled[row.merchant])}
                      onChange={(event) => setCancelled({ ...cancelled, [row.merchant]: event.target.checked })}
                      style={{ accentColor: "#0099FF" }}
                    />
                    {row.merchant} ({money(row.monthly_cents)})
                  </label>
                ))}
              </div>
            </fieldset>
          )}
        </div>
        <div className="stack" aria-live="polite">
          {failure && <PageError message={failure} />}
          {result ? (
            <>
              <div className="stat-row">
                <div>
                  <div className="stat-label">Change each month</div>
                  <div className="stat-value">{money(result.monthly_delta_cents, true)}</div>
                </div>
                <div>
                  <div className="stat-label">Over a year</div>
                  <div className="stat-value">{money(result.yearly_delta_cents, true)}</div>
                </div>
              </div>
              <p className="small muted">
                Your typical monthly surplus goes from {money(result.baseline.net_cents, true)} to {money(result.scenario.net_cents, true)}.
              </p>
              <ScenarioChart rows={result.series.map((row) => ({ label: row.month, baseline_cents: row.baseline_cents, scenario_cents: row.scenario_cents }))} />
            </>
          ) : (
            <p className="muted">Move a slider or pick a subscription to see how your next 12 months change.</p>
          )}
        </div>
      </div>
    </section>
  );
}

const VERDICT: Record<AffordResult["verdict"], string> = {
  yes: "Yes, from your monthly surplus",
  yes_with_savings: "Yes, using some of your balance",
  with_cuts: "Yes, with a few changes",
  not_yet: "Not by that date",
};

function Afford() {
  const money = useMoney();
  const [amount, setAmount] = useState("1500");
  const [by, setBy] = useState("");
  const [result, setResult] = useState<AffordResult | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  async function check(event: React.FormEvent) {
    event.preventDefault();
    const cents = parseDollars(amount);
    if (cents === null || cents <= 0) {
      setFailure("Enter a dollar amount above zero.");
      return;
    }
    setFailure(null);
    try {
      setResult(await send<AffordResult>("/api/afford", "POST", { amount_cents: cents, by: by || null }));
    } catch (caught) {
      setFailure((caught as Error).message);
    }
  }

  return (
    <section className="section panel" aria-labelledby="afford">
      <h2 id="afford">Can I afford it?</h2>
      <form className="grid-form" onSubmit={check}>
        <label className="field">
          Cost
          <input className="input" inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} />
        </label>
        <label className="field">
          Needed by
          <input className="input" type="date" value={by} onChange={(event) => setBy(event.target.value)} />
        </label>
        <button className="btn" type="submit">
          Check
        </button>
      </form>
      {failure && <PageError message={failure} />}
      {result && (
        <div className="stack" style={{ gap: 6 }} aria-live="polite">
          <h3 style={{ fontSize: "1.3rem" }}>{VERDICT[result.verdict]}</h3>
          <p>
            That takes {money(result.required_monthly_cents)} a month until {monthYear(result.by)}, and you have about {money(result.monthly_surplus_cents, true)} a month free after your goals.
            {result.has_balance && result.spare_balance_cents > 0 ? ` You also have ${money(result.spare_balance_cents, true)} of balance beyond a one-month cushion.` : ""}
          </p>
          {result.suggested_cuts.length > 0 && (
            <p>Trim {result.suggested_cuts.map((cut) => `${cut.category} by ${money(cut.cut_cents, true)}`).join(" and ")} a month.</p>
          )}
          {result.earliest_date && <p>With some trimming, {monthYear(result.earliest_date)} looks realistic.</p>}
        </div>
      )}
    </section>
  );
}

export default function PlanPage() {
  const money = useMoney();
  const { data: forecast, error, reload } = useFetch<Forecast>("/api/forecast");
  const { data: recurring } = useFetch<Recurring>("/api/recurring");
  const { data: budgets } = useFetch<{ suggestions: Suggestion[] }>("/api/budgets");

  return (
    <div className="page stack" style={{ gap: 40 }}>
      <div className="page-head" style={{ marginBottom: 0 }}>
        <div>
          <h1>Plan</h1>
          <p className="muted">See where your balance is heading, and try changes before you make them.</p>
        </div>
      </div>
      {error && <PageError message={error} onRetry={reload} />}

      {forecast && forecast.needs_balance && (
        <div className="empty">
          <h2>Add your balance to see a forecast</h2>
          <Link className="btn" href="/settings">
            Add your balance
          </Link>
        </div>
      )}

      {forecast && !forecast.needs_balance && (
        <div className="split">
          <section className="section" aria-labelledby="forecast-head">
            <h2 id="forecast-head">Next 45 days</h2>
            <ForecastChart points={forecast.points} height={280} />
            <p className="small muted">The shaded band shows the likely range. The red dot marks your lowest expected balance.</p>
            <details className="numbers">
              <summary>Show the numbers</summary>
              <div className="table-wrap" style={{ maxHeight: 260, overflowY: "auto" }}>
                <table>
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th className="amount">Expected balance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {forecast.points.map((point) => (
                      <tr key={point.date}>
                        <td>{longDate(point.date)}</td>
                        <td className="amount">{money(point.balance_cents, true)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </section>
          <section className="section" aria-labelledby="upcoming-head">
            <h2 id="upcoming-head">Coming up</h2>
            {forecast.upcoming.length ? (
              <ul className="rule-list">
                {forecast.upcoming.slice(0, 9).map((event) => (
                  <li key={`${event.merchant}${event.date}`} className="bar-labels">
                    <span>
                      {event.merchant} <span className="muted small">{shortDate(event.date)}</span>
                    </span>
                    <strong className={event.amount_cents > 0 ? "tone-good" : ""}>{money(event.amount_cents)}</strong>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">No regular bills found yet. About three months of history helps Cirrus spot them.</p>
            )}
          </section>
        </div>
      )}

      {recurring && budgets && <Simulator suggestions={budgets.suggestions} streams={recurring.streams} />}
      <Afford />

      {recurring && recurring.streams.some((row) => row.direction === "out" && row.active) && (
        <section className="section" aria-labelledby="regular-head">
          <div className="section-head">
            <h2 id="regular-head">Regular costs</h2>
            <span className="small muted">
              {money(recurring.subscriptions_monthly_cents + recurring.bills_monthly_cents, true)} a month
            </span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>How often</th>
                  <th>Next</th>
                  <th className="amount">Amount</th>
                </tr>
              </thead>
              <tbody>
                {recurring.streams
                  .filter((row) => row.direction === "out" && row.active)
                  .map((row) => (
                    <tr key={row.merchant}>
                      <td>
                        {row.merchant}
                        {row.price_change_cents > 0 && <span className="small tone-alert"> up {money(row.price_change_cents)}</span>}
                      </td>
                      <td>{row.cadence}</td>
                      <td>{shortDate(row.next_date)}</td>
                      <td className="amount">{money(row.amount_cents)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
