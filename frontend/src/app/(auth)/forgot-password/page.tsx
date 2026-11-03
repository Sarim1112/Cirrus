"use client";

import Link from "next/link";
import { useState } from "react";
import { AuthFrame } from "@/components/AuthFrame";
import { PageError } from "@/components/ui";
import { send } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setFailure(null);
    try {
      await send("/api/auth/forgot-password", "POST", { email });
      setSent(true);
    } catch (caught) {
      setFailure((caught as Error).message);
    }
  }

  return (
    <AuthFrame>
      <h1>Reset your password</h1>
      {sent ? (
        <p className="form-ok" role="status">
          If {email} has an account, a reset link is on its way. It expires in one hour.
        </p>
      ) : (
        <form className="stack" onSubmit={submit}>
          <label className="field">
            Email
            <input className="input" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>
          {failure && <PageError message={failure} />}
          <button className="btn" type="submit">
            Send reset link
          </button>
        </form>
      )}
      <p className="small">
        <Link href="/login">Back to sign in</Link>
      </p>
    </AuthFrame>
  );
}
