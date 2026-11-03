"use client";

import { Download, Sparkles, Trash2 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { PageError, Toast } from "@/components/ui";
import { useMoney } from "@/components/UserContext";
import { send, useFetch } from "@/lib/api";
import { longDate } from "@/lib/format";
import type { Txn } from "@/lib/types";

type Page = { total: number; page: number; page_size: number; items: Txn[] };

function TransactionsInner() {
  const router = useRouter();
  const params = useSearchParams();
  const money = useMoney();
  const [search, setSearch] = useState(params.get("q") ?? "");
  const [page, setPage] = useState(1);
  const [toast, setToast] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const clearToast = useCallback(() => setToast(null), []);

  const category = params.get("category") ?? "";
  const month = params.get("month") ?? "";
  const ids = params.get("ids") ?? "";
  const q = params.get("q") ?? "";

  const setFilter = useCallback(
    (key: string, value: string) => {
      const next = new URLSearchParams(params.toString());
      if (value) next.set(key, value);
      else next.delete(key);
      next.delete("ids");
      setPage(1);
      router.replace(`/transactions?${next.toString()}`);
    },
    [params, router],
  );

  useEffect(() => {
    const timer = setTimeout(() => {
      if (search !== q) setFilter("q", search);
    }, 300);
    return () => clearTimeout(timer);
  }, [search, q, setFilter]);

  const query = useMemo(() => {
    const next = new URLSearchParams();
    if (q) next.set("q", q);
    if (category) next.set("category", category);
    if (month) next.set("month", month);
    if (ids) next.set("ids", ids);
    next.set("page", String(page));
    return next.toString();
  }, [q, category, month, ids, page]);

  const { data, error, reload } = useFetch<Page>(`/api/transactions?${query}`);
  const { data: categories } = useFetch<{ categories: string[] }>("/api/categories");
  const { data: status } = useFetch<{ mode: string }>("/api/chat/status");

  async function recategorize(txn: Txn, next: string) {
    const result = await send<{ updated: number }>(`/api/transactions/${txn.id}`, "PATCH", { category: next, apply_to_merchant: true });
    setToast(`${txn.merchant} is now ${next}. Updated ${result.updated} ${result.updated === 1 ? "transaction" : "transactions"}, and future imports will follow.`);
    await reload();
  }

  async function remove(txn: Txn) {
    await send(`/api/transactions/${txn.id}`, "DELETE");
    setToast(`Deleted ${txn.merchant}.`);
    await reload();
  }

  async function aiCategorize() {
    setBusy(true);
    try {
      const result = await send<{ updated: number; merchants: number }>("/api/transactions/categorize-with-ai", "POST");
      setToast(result.updated ? `Sorted ${result.updated} transactions from ${result.merchants} merchants.` : "Nothing more to sort.");
      await reload();
    } catch (caught) {
      setToast((caught as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const totalPages = data ? Math.max(Math.ceil(data.total / data.page_size), 1) : 1;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Transactions</h1>
          <p className="muted">Change a category once, and Cirrus remembers it for that merchant.</p>
        </div>
        <div className="row">
          {status?.mode === "local_ai" && (
            <button className="btn quiet" onClick={aiCategorize} disabled={busy}>
              <Sparkles size={17} aria-hidden="true" />
              {busy ? "Sorting" : "Sort uncategorized with AI"}
            </button>
          )}
          <a className="btn quiet" href="/api/transactions/export.csv">
            <Download size={17} aria-hidden="true" />
            Export CSV
          </a>
        </div>
      </div>

      <div className="filters">
        <label className="search">
          <span className="sr-only">Search merchants</span>
          <input className="input" type="search" placeholder="Search merchants" value={search} onChange={(event) => setSearch(event.target.value)} />
        </label>
        <label>
          <span className="sr-only">Filter by category</span>
          <select className="select" value={category} onChange={(event) => setFilter("category", event.target.value)}>
            <option value="">All categories</option>
            {categories?.categories.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </label>
        <label>
          <span className="sr-only">Filter by month</span>
          <input className="input" type="month" value={month} onChange={(event) => setFilter("month", event.target.value)} />
        </label>
      </div>

      {ids && (
        <p className="form-ok" style={{ marginBottom: 14 }}>
          Showing the transactions behind an insight.{" "}
          <button className="link-btn" onClick={() => router.replace("/transactions")}>
            Show all
          </button>
        </p>
      )}
      {error && <PageError message={error} onRetry={reload} />}
      {data && data.items.length === 0 && (
        <div className="empty">
          <h2>No transactions match</h2>
          <p className="muted">Try a different search, or import another statement.</p>
        </div>
      )}
      {data && data.items.length > 0 && (
        <table className="responsive-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Merchant</th>
              <th>Category</th>
              <th className="amount">Amount</th>
              <th>
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((txn) => (
              <tr key={txn.id}>
                <td className="cell-date">{longDate(txn.date)}</td>
                <td className="cell-merchant">
                  <span className="txn-merchant">{txn.merchant}</span>
                  <span className="txn-raw" title={txn.raw_description}>
                    {txn.raw_description}
                  </span>
                </td>
                <td className="cell-category">
                  <select
                    className="category-select"
                    aria-label={`Category for ${txn.merchant}`}
                    value={txn.category}
                    onChange={(event) => recategorize(txn, event.target.value)}
                  >
                    {categories?.categories.map((name) => (
                      <option key={name}>{name}</option>
                    ))}
                    {!categories && <option>{txn.category}</option>}
                  </select>
                </td>
                <td className={`amount ${txn.amount_cents > 0 ? "in" : ""}`}>{money(txn.amount_cents)}</td>
                <td className="cell-actions">
                  <button className="icon-btn ghost" onClick={() => remove(txn)} aria-label={`Delete ${txn.merchant} on ${longDate(txn.date)}`}>
                    <Trash2 size={16} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data && data.total > data.page_size && (
        <nav className="pager" aria-label="Pages">
          <button className="btn quiet" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Newer
          </button>
          <span className="small muted">
            Page {page} of {totalPages}
          </span>
          <button className="btn quiet" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
            Older
          </button>
        </nav>
      )}
      <Toast message={toast} onDone={clearToast} />
    </div>
  );
}

export default function TransactionsPage() {
  return (
    <Suspense>
      <TransactionsInner />
    </Suspense>
  );
}
