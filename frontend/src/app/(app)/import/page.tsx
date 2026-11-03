"use client";

import { FileUp } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { PageError, Toast } from "@/components/ui";
import { useMoney } from "@/components/UserContext";
import { api, send, useFetch } from "@/lib/api";
import { longDate } from "@/lib/format";
import type { ImportBatch, ImportPreview } from "@/lib/types";

export default function ImportPage() {
  const money = useMoney();
  const { data: history, reload } = useFetch<{ imports: ImportBatch[] }>("/api/imports");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [dateOrder, setDateOrder] = useState("auto");
  const [reverse, setReverse] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [done, setDone] = useState<ImportBatch | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const clearToast = useCallback(() => setToast(null), []);

  const form = useCallback(() => {
    const body = new FormData();
    if (file) body.set("file", file);
    body.set("date_order", dateOrder);
    body.set("reverse_amounts", String(reverse));
    return body;
  }, [file, dateOrder, reverse]);

  useEffect(() => {
    if (!file) return;
    let cancelled = false;
    (async () => {
      setBusy(true);
      setFailure(null);
      try {
        const result = await api<ImportPreview>("/api/imports/preview", { method: "POST", body: form() });
        if (!cancelled) setPreview(result);
      } catch (caught) {
        if (!cancelled) {
          setPreview(null);
          setFailure((caught as Error).message);
        }
      } finally {
        if (!cancelled) setBusy(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [file, form]);

  function choose(next: File | undefined | null) {
    if (!next) return;
    setDone(null);
    setDateOrder("auto");
    setReverse(false);
    setFile(next);
  }

  async function confirm() {
    setBusy(true);
    setFailure(null);
    try {
      const batch = await api<ImportBatch>("/api/imports", { method: "POST", body: form() });
      setDone(batch);
      setFile(null);
      setPreview(null);
      await reload();
    } catch (caught) {
      setFailure((caught as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function undo(batch: ImportBatch) {
    await send(`/api/imports/${batch.id}`, "DELETE");
    if (done?.id === batch.id) setDone(null);
    setToast(`Removed ${batch.filename} and its transactions.`);
    await reload();
  }

  return (
    <div className="page stack" style={{ gap: 30 }}>
      <div className="page-head" style={{ marginBottom: 0 }}>
        <div>
          <h1>Import a statement</h1>
          <p className="muted">Download a CSV or PDF from your bank&apos;s website. Nothing is saved until you check the preview and confirm.</p>
        </div>
      </div>

      {done && (
        <div className="form-ok" role="status">
          Imported {done.rows_imported} transactions from {done.filename}
          {done.rows_duplicate ? `, and skipped ${done.rows_duplicate} you already had` : ""}. <Link href="/overview">See your overview</Link>
        </div>
      )}
      {failure && <PageError message={failure} />}

      {!preview && (
        <label
          className={`dropzone ${dragging ? "active" : ""}`}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            choose(event.dataTransfer.files[0]);
          }}
        >
          <FileUp size={30} aria-hidden="true" />
          <strong>{busy ? "Reading your statement" : "Choose a CSV or PDF"}</strong>
          <span className="small muted">Or drag it here. Up to 10 MB.</span>
          <input
            ref={input}
            className="sr-only"
            type="file"
            accept=".csv,.txt,.tsv,.pdf"
            onChange={(event) => {
              choose(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
        </label>
      )}

      {preview && (
        <section className="section" aria-labelledby="check">
          <div className="section-head">
            <h2 id="check">Check this looks right</h2>
            <button className="link-btn" onClick={() => { setPreview(null); setFile(null); }}>
              Choose another file
            </button>
          </div>
          <div className="stat-row">
            <div>
              <div className="stat-label">Transactions</div>
              <div className="stat-value">{preview.rows}</div>
            </div>
            <div>
              <div className="stat-label">Dates</div>
              <div className="stat-value" style={{ fontSize: "1.15rem", lineHeight: 2 }}>
                {longDate(preview.first_date)} to {longDate(preview.last_date)}
              </div>
            </div>
            <div>
              <div className="stat-label">Already imported</div>
              <div className="stat-value">{preview.duplicates}</div>
            </div>
            <div>
              <div className="stat-label">Couldn&apos;t sort yet</div>
              <div className="stat-value">{preview.uncategorized}</div>
            </div>
          </div>

          {preview.warnings.map((warning) => (
            <p className="form-ok" key={warning}>
              {warning}
            </p>
          ))}

          <div className="grid-form">
            <label className="field">
              Date order
              <select className="select" value={dateOrder === "auto" ? preview.date_order : dateOrder} onChange={(event) => setDateOrder(event.target.value)}>
                <option value="mdy">Month / day / year</option>
                <option value="dmy">Day / month / year</option>
                <option value="ymd">Year-month-day</option>
              </select>
            </label>
            <label className="row" style={{ fontWeight: 600, minHeight: 44 }}>
              <input type="checkbox" checked={reverse} onChange={(event) => setReverse(event.target.checked)} style={{ accentColor: "#0099FF", width: 18, height: 18 }} />
              Reverse amounts
            </label>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>On your statement</th>
                  <th>Merchant</th>
                  <th>Category</th>
                  <th className="amount">Amount</th>
                </tr>
              </thead>
              <tbody>
                {preview.sample.map((row, index) => (
                  <tr key={index}>
                    <td style={{ whiteSpace: "nowrap" }}>{row.date}</td>
                    <td className="small muted">{row.description}</td>
                    <td>{row.merchant}</td>
                    <td>{row.category}</td>
                    <td className={`amount ${row.amount_cents > 0 ? "in" : ""}`}>{money(row.amount_cents)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {preview.rows > preview.sample.length && <p className="small muted">Showing the first {preview.sample.length} of {preview.rows}.</p>}
          <div className="row">
            <button className="btn" onClick={confirm} disabled={busy}>
              {busy ? "Importing" : `Import ${preview.rows - preview.duplicates} transactions`}
            </button>
          </div>
        </section>
      )}

      {history && history.imports.length > 0 && (
        <section className="section" aria-labelledby="past">
          <h2 id="past">Past imports</h2>
          <ul className="rule-list">
            {history.imports.map((batch) => (
              <li className="bar-labels" key={batch.id}>
                <span>
                  {batch.filename}{" "}
                  <span className="small muted">
                    {batch.rows_imported} transactions, {longDate(batch.created_at)}
                  </span>
                </span>
                <button className="link-btn small" onClick={() => undo(batch)}>
                  Undo import
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      <Toast message={toast} onDone={clearToast} />
    </div>
  );
}
