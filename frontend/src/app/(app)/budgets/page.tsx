"use client";

import { useCallback, useState } from "react";
import { BudgetMeter, PageError, Toast } from "@/components/ui";
import { useMoney } from "@/components/UserContext";
import { send, useFetch } from "@/lib/api";
import { parseDollars } from "@/lib/format";
import type { BudgetRow, Suggestion } from "@/lib/types";

type Data = { status: (BudgetRow & { txn_ids: string[] })[]; suggestions: Suggestion[] };

const KIND = { fixed: "Fixed bill", flexible: "Flexible", occasional: "Occasional" };

export default function BudgetsPage() {
  const money = useMoney();
  const { data, error, reload } = useFetch<Data>("/api/budgets");
  const [toast, setToast] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const clearToast = useCallback(() => setToast(null), []);

  async function save(rows: { category: string; limit_cents: number }[], message: string) {
    setProblem(null);
    try {
      await send("/api/budgets", "PUT", { budgets: rows });
      setToast(message);
      await reload();
    } catch (caught) {
      setProblem((caught as Error).message);
    }
  }

  const current = data?.status.map((row) => ({ category: row.category, limit_cents: row.limit_cents })) ?? [];

  function setLimit(category: string, value: string) {
    const cents = parseDollars(value);
    if (cents === null || cents <= 0) {
      setProblem(`Enter a dollar amount above zero for ${category}.`);
      return;
    }
    void save(
      [...current.filter((row) => row.category !== category), { category, limit_cents: cents }],
      `${category} budget saved.`,
    );
  }

  function applyAll() {
    if (!data) return;
    void save(
      data.suggestions.map((row) => ({ category: row.category, limit_cents: row.limit_cents })),
      "Suggested budgets applied.",
    );
  }

  return (
    <div className="page stack" style={{ gap: 36 }}>
      <div className="page-head" style={{ marginBottom: 0 }}>
        <div>
          <h1>Budgets</h1>
          <p className="muted">Targets come from your own history, so they&apos;re realistic for how you actually live.</p>
        </div>
      </div>
      {error && <PageError message={error} onRetry={reload} />}
      {problem && <PageError message={problem} />}

      {data && data.status.length > 0 && (
        <section className="section" aria-labelledby="month-budget">
          <h2 id="month-budget">This month</h2>
          <div className="bars">
            {data.status.map((row) => (
              <div className="stack" style={{ gap: 3 }} key={row.category}>
                <BudgetMeter row={row} />
                <p className="small muted">
                  {row.status === "over"
                    ? `${money(-row.remaining_cents)} over.`
                    : row.status === "watch"
                      ? `${money(row.remaining_cents)} left, likely to finish near ${money(row.projected_cents, true)}.`
                      : `${money(row.remaining_cents)} left.`}{" "}
                  <button className="link-btn" onClick={() => save(current.filter((item) => item.category !== row.category), `${row.category} budget removed.`)}>
                    Remove
                  </button>
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      {data && data.suggestions.length > 0 && (
        <section className="section" aria-labelledby="suggested">
          <div className="section-head">
            <h2 id="suggested">Suggested for you</h2>
            <button className="btn" onClick={applyAll}>
              Use all suggestions
            </button>
          </div>
          <ul className="rule-list">
            {data.suggestions.map((row) => {
              const existing = current.find((item) => item.category === row.category);
              return (
                <li key={row.category} className="stack" style={{ gap: 6 }}>
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <span>
                      <strong>{row.category}</strong> <span className="small muted">{KIND[row.kind]}</span>
                    </span>
                    <form
                      className="row"
                      style={{ gap: 8 }}
                      onSubmit={(event) => {
                        event.preventDefault();
                        const value = new FormData(event.currentTarget).get("limit");
                        setLimit(row.category, String(value));
                      }}
                    >
                      <label>
                        <span className="sr-only">Monthly budget for {row.category}</span>
                        <input
                          key={existing?.limit_cents ?? row.limit_cents}
                          name="limit"
                          className="input"
                          style={{ width: 104 }}
                          inputMode="decimal"
                          defaultValue={((existing?.limit_cents ?? row.limit_cents) / 100).toFixed(0)}
                        />
                      </label>
                      <button className="btn quiet" type="submit">
                        {existing ? "Update" : "Set"}
                      </button>
                    </form>
                  </div>
                  <p className="small muted">{row.reason}</p>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {data && data.suggestions.length === 0 && data.status.length === 0 && (
        <div className="empty">
          <h2>Not enough history yet</h2>
          <p className="muted">Import at least one complete month of transactions to get budget suggestions.</p>
          <a className="btn" href="/import">
            Import a statement
          </a>
        </div>
      )}
      <Toast message={toast} onDone={clearToast} />
    </div>
  );
}
