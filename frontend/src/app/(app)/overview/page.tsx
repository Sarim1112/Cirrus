"use client";

import Link from "next/link";
import { useMemo } from "react";
import { CashflowChart, HBars, Horizon } from "@/components/charts";
import { DemoButton } from "@/components/DemoButton";
import { BudgetMeter, InsightItem, PageError } from "@/components/ui";
import { useMoney, useUser } from "@/components/UserContext";
import { useFetch } from "@/lib/api";
import { longDate, shortDate } from "@/lib/format";
import type { Forecast, Overview } from "@/lib/types";

function SkyBand({ forecast, name }: { forecast: Forecast; name: string }) {
  const money = useMoney();
  const safe = forecast.safe_to_spend;
  const greeting = name ? `Hi ${name}.` : "Hi there.";

  if (!safe) {
    return (
      <section className="sky-band">
        <div className="sky-copy" style={{ paddingBottom: 30 }}>
          <p className="sky-greeting">{greeting}</p>
          <h1 className="sky-headline">Add your balance to see what&apos;s safe to spend.</h1>
          <p className="sky-sub">
            Your everyday spending runs about {money(forecast.daily_variable_cents, true)} a day. With your balance, Cirrus can forecast the weeks ahead.
          </p>
          <div className="sky-actions">
            <Link href="/settings">Add your balance</Link>
          </div>
        </div>
      </section>
    );
  }

  const until = safe.until_kind === "payday" ? `payday, ${shortDate(safe.until)}` : shortDate(safe.until);
  const low = forecast.low_point;
  const lowIndex = low ? forecast.points.findIndex((p) => p.date === low.date) : -1;
  const lowLeft = lowIndex >= 0 ? (lowIndex / Math.max(forecast.points.length - 1, 1)) * 100 : 50;
  const values = forecast.points.map((p) => p.balance_cents);
  const top = Math.max(...values);
  const bottom = Math.min(...values);
  const pad = Math.max((top - bottom) * 0.25, 5000);
  const lowHeight = low ? (low.balance_cents - (bottom - pad)) / (top - bottom + 2 * pad) : 0;

  return (
    <section className="sky-band">
      <div className="sky-copy">
        <p className="sky-greeting">{greeting}</p>
        <h1 className="sky-headline">
          {safe.shortfall_cents
            ? `You're ${money(safe.shortfall_cents, true)} short before ${until}.`
            : `${money(safe.amount_cents, true)} is safe to spend until ${until}.`}
        </h1>
        <p className="sky-sub">
          Your {money(safe.breakdown.balance_cents, true)} balance, minus {money(safe.breakdown.bills_cents + safe.breakdown.held_back_cents, true)} for upcoming bills
          {safe.breakdown.goals_cents ? `, ${money(safe.breakdown.goals_cents, true)} for goals` : ""} and your {money(safe.breakdown.buffer_cents, true)} buffer.
        </p>
        <div className="sky-actions">
          <Link href="/plan">See the forecast</Link>
          <Link href="/advisor">Ask the advisor</Link>
        </div>
      </div>
      <div className="horizon">
        {low && (
          <span className="horizon-tag" style={{ left: `clamp(100px, ${lowLeft}%, calc(100% - 100px))`, top: `calc(30px + (100% - 30px) * ${1 - lowHeight} - 38px)` }}>
            Lowest: {money(low.balance_cents, true)} on {shortDate(low.date)}
          </span>
        )}
        <Horizon points={forecast.points} low={low} />
      </div>
      <p className="sr-only">
        Your balance is forecast over the next {forecast.points.length} days.
        {low ? ` The lowest point is ${money(low.balance_cents)} on ${shortDate(low.date)}.` : ""}
      </p>
    </section>
  );
}

export default function OverviewPage() {
  const { user } = useUser();
  const money = useMoney();
  const { data, error, reload } = useFetch<Overview>("/api/overview");

  const dayFraction = useMemo(() => {
    if (!data) return undefined;
    const [year, month, day] = data.today.split("-").map(Number);
    return day / new Date(year, month, 0).getDate();
  }, [data]);

  if (error) {
    return (
      <div className="page">
        <PageError message={error} onRetry={reload} />
      </div>
    );
  }
  if (!data) {
    return (
      <div className="page">
        <div className="skeleton" role="status" aria-label="Loading your overview" />
      </div>
    );
  }

  if (!data.has_data) {
    return (
      <div className="page">
        <div className="page-head">
          <div>
            <h1>Start with a statement</h1>
            <p className="muted">Download a CSV or PDF from your bank. Cirrus cleans it up, sorts it into categories and starts finding patterns.</p>
          </div>
        </div>
        <div className="empty">
          <h2>Your overview will appear here</h2>
          <p className="muted">About three months of history gives the best results.</p>
          <div className="row">
            <Link className="btn" href="/import">
              Import a statement
            </Link>
            {!user.is_demo && <DemoButton className="btn quiet" label="Explore sample data instead" />}
          </div>
        </div>
      </div>
    );
  }

  const change = data.this_month.spending_cents - data.last_month.spending_cents;
  const main = data.insights.filter((insight) => insight.severity !== "good").slice(0, 4);

  return (
    <>
      <SkyBand forecast={data.forecast} name={user.display_name} />
      <div className="page stack" style={{ gap: 40 }}>
        {data.forecast.stale_days > 14 && data.forecast.latest_data_date && (
          <p className="form-ok">
            Your newest transaction is from {longDate(data.forecast.latest_data_date)}, so this forecast may be out of date. <Link href="/import">Import a newer statement</Link>
          </p>
        )}
        <div className="stat-row">
          <div>
            <div className="stat-label">Spent this month</div>
            <div className="stat-value">{money(data.this_month.spending_cents, true)}</div>
          </div>
          <div>
            <div className="stat-label">Last month</div>
            <div className="stat-value">{money(data.last_month.spending_cents, true)}</div>
          </div>
          <div>
            <div className="stat-label">Typical month left over</div>
            <div className="stat-value">{money(data.average.net_cents, true)}</div>
          </div>
          {data.forecast.month_end_balance_cents !== null && (
            <div>
              <div className="stat-label">Expected month-end balance</div>
              <div className="stat-value">{money(data.forecast.month_end_balance_cents, true)}</div>
            </div>
          )}
        </div>
        <span className="sr-only">
          This month is {money(Math.abs(change), true)} {change > 0 ? "above" : "below"} last month so far.
        </span>

        <div className="split">
          <section className="section" aria-labelledby="insights-head">
            <div className="section-head">
              <h2 id="insights-head">Worth a look</h2>
            </div>
            {main.length ? (
              <ul className="rule-list">
                {main.map((insight) => (
                  <InsightItem key={insight.key} insight={insight} onDismiss={reload} />
                ))}
              </ul>
            ) : (
              <p className="muted">Nothing unusual right now. Your recent spending looks normal for you.</p>
            )}
          </section>

          <section className="section" aria-labelledby="month-head">
            <div className="section-head">
              <h2 id="month-head">This month by category</h2>
              <Link className="small" href="/transactions">
                All transactions
              </Link>
            </div>
            {data.categories.length ? (
              <HBars rows={data.categories.slice(0, 7).map((row) => ({ label: row.name, value_cents: row.amount_cents }))} />
            ) : (
              <p className="muted">No spending yet this month.</p>
            )}
          </section>
        </div>

        <div className="split">
          <section className="section" aria-labelledby="flow-head">
            <h2 id="flow-head">Income and spending</h2>
            <CashflowChart rows={data.series.map((row) => ({ label: row.month, income_cents: row.income_cents, spending_cents: row.spending_cents }))} />
            <details className="numbers">
              <summary>Show the numbers</summary>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Month</th>
                      <th className="amount">Income</th>
                      <th className="amount">Spending</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.series.map((row) => (
                      <tr key={row.month}>
                        <td>{row.month}</td>
                        <td className="amount">{money(row.income_cents)}</td>
                        <td className="amount">{money(row.spending_cents)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </section>

          <section className="section" aria-labelledby="budget-head">
            <div className="section-head">
              <h2 id="budget-head">Budgets</h2>
              <Link className="small" href="/budgets">
                Manage
              </Link>
            </div>
            {data.budgets.length ? (
              <div className="bars">
                {data.budgets.map((row) => (
                  <BudgetMeter key={row.category} row={row} dayFraction={dayFraction} />
                ))}
                <p className="small muted">The dark line marks how far through the month you are.</p>
              </div>
            ) : (
              <p className="muted">
                No budgets yet. <Link href="/budgets">Get suggestions based on your own spending.</Link>
              </p>
            )}
          </section>
        </div>
      </div>
    </>
  );
}
