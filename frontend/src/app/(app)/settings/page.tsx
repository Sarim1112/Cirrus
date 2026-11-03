"use client";

import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { PageError, PasswordField, Toast } from "@/components/ui";
import { useUser } from "@/components/UserContext";
import { send, useFetch } from "@/lib/api";
import { parseDollars } from "@/lib/format";

const CURRENCIES = ["CAD", "USD", "EUR", "GBP", "AUD", "AED", "SAR", "PKR", "INR"];

export default function SettingsPage() {
  const router = useRouter();
  const { user, refreshUser } = useUser();
  const { data: status } = useFetch<{ mode: string; model: string | null }>("/api/chat/status");
  const [name, setName] = useState(user.display_name);
  const [currency, setCurrency] = useState(user.currency);
  const [balance, setBalance] = useState(user.balance_cents === null ? "" : (user.balance_cents / 100).toFixed(2));
  const [buffer, setBuffer] = useState((user.safety_buffer_cents / 100).toFixed(0));
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [deletePassword, setDeletePassword] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [passwordFailure, setPasswordFailure] = useState<string | null>(null);
  const [deleteFailure, setDeleteFailure] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const clearToast = useCallback(() => setToast(null), []);

  async function saveProfile(event: React.FormEvent) {
    event.preventDefault();
    const bufferCents = parseDollars(buffer);
    if (bufferCents === null || bufferCents < 0) {
      setFailure("Enter a safety buffer of zero or more.");
      return;
    }
    const balanceCents = balance.trim() ? parseDollars(balance) : null;
    if (balance.trim() && balanceCents === null) {
      setFailure("Enter your balance as a number, such as 1250.00.");
      return;
    }
    const changedBalance = balanceCents !== user.balance_cents;
    try {
      await send("/api/account/settings", "PATCH", {
        display_name: name,
        currency,
        safety_buffer_cents: bufferCents,
        ...(changedBalance ? (balanceCents === null ? { clear_balance: true } : { balance_cents: balanceCents }) : {}),
      });
      await refreshUser();
      setFailure(null);
      setToast("Settings saved.");
    } catch (caught) {
      setFailure((caught as Error).message);
    }
  }

  async function changePassword(event: React.FormEvent) {
    event.preventDefault();
    try {
      await send("/api/auth/change-password", "POST", { current_password: current, new_password: next });
      setCurrent("");
      setNext("");
      setPasswordFailure(null);
      setToast("Password changed. Other devices have been signed out.");
    } catch (caught) {
      setPasswordFailure((caught as Error).message);
    }
  }

  async function deleteAccount(event: React.FormEvent) {
    event.preventDefault();
    try {
      await send("/api/account/delete", "POST", { password: deletePassword });
      router.push("/");
    } catch (caught) {
      setDeleteFailure((caught as Error).message);
    }
  }

  return (
    <div className="page stack" style={{ gap: 36, maxWidth: 720 }}>
      <h1>Settings</h1>

      <section className="section" aria-labelledby="profile">
        <h2 id="profile">Your details</h2>
        <form className="stack" onSubmit={saveProfile}>
          <div className="grid-form">
            <label className="field">
              Name
              <input className="input" maxLength={80} value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <label className="field">
              Currency
              <select className="select" value={currency} onChange={(event) => setCurrency(event.target.value)}>
                {CURRENCIES.map((code) => (
                  <option key={code}>{code}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="grid-form">
            <label className="field">
              Current balance
              <input className="input" inputMode="decimal" placeholder="1250.00" value={balance} onChange={(event) => setBalance(event.target.value)} />
              <span className="hint">Used for your forecast. Imported statements can update it.</span>
            </label>
            <label className="field">
              Safety buffer
              <input className="input" inputMode="decimal" value={buffer} onChange={(event) => setBuffer(event.target.value)} />
              <span className="hint">Kept out of what&apos;s safe to spend.</span>
            </label>
          </div>
          {failure && <PageError message={failure} />}
          <div>
            <button className="btn" type="submit">
              Save settings
            </button>
          </div>
        </form>
      </section>

      <section className="section" aria-labelledby="ai">
        <h2 id="ai">AI</h2>
        <p className="muted">
          {status?.mode === "local_ai"
            ? `The advisor is using ${status.model}, running on this Cirrus server. Your data isn't sent to an outside AI service.`
            : "No local AI model is connected, so the advisor uses its built-in answers. Every figure works the same way, and your data isn't sent to an AI service."}
        </p>
      </section>

      {!user.is_demo && (
        <section className="section" aria-labelledby="password">
          <h2 id="password">Change password</h2>
          <form className="stack" onSubmit={changePassword}>
            <PasswordField label="Current password" value={current} onChange={setCurrent} autoComplete="current-password" />
            <PasswordField label="New password" value={next} onChange={setNext} autoComplete="new-password" hint="At least 10 characters." />
            {passwordFailure && <PageError message={passwordFailure} />}
            <div>
              <button className="btn quiet" type="submit">
                Change password
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="section" aria-labelledby="data">
        <h2 id="data">Your data</h2>
        <div className="row">
          <a className="btn quiet" href="/api/account/export" download="cirrus-data.json">
            Download all my data
          </a>
          <a className="btn quiet" href="/api/transactions/export.csv">
            Download transactions as CSV
          </a>
        </div>
      </section>

      <section className="section" aria-labelledby="delete">
        <h2 id="delete">{user.is_demo ? "End the demo" : "Delete account"}</h2>
        <p className="muted">
          {user.is_demo
            ? "This deletes the sample data right away."
            : "This permanently deletes your account, transactions, budgets, goals and chat history. It can't be undone."}
        </p>
        {!confirming ? (
          <div>
            <button className="btn danger" onClick={() => setConfirming(true)}>
              {user.is_demo ? "End the demo" : "Delete my account"}
            </button>
          </div>
        ) : (
          <form className="stack" onSubmit={deleteAccount}>
            {!user.is_demo && <PasswordField label="Enter your password to confirm" value={deletePassword} onChange={setDeletePassword} autoComplete="current-password" />}
            {deleteFailure && <PageError message={deleteFailure} />}
            <div className="row">
              <button className="btn danger" type="submit">
                {user.is_demo ? "End the demo now" : "Permanently delete my account"}
              </button>
              <button className="btn quiet" type="button" onClick={() => setConfirming(false)}>
                Keep it
              </button>
            </div>
          </form>
        )}
      </section>
      <Toast message={toast} onDone={clearToast} />
    </div>
  );
}
