"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuthFrame } from "@/components/AuthFrame";
import { PageError, PasswordField } from "@/components/ui";
import { send } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFailure(null);
    try {
      // A demo session is replaced by this new account's session.
      await send("/api/auth/register", "POST", { email, password, display_name: name });
      router.push("/import");
    } catch (caught) {
      setFailure((caught as Error).message);
      setBusy(false);
    }
  }

  return (
    <AuthFrame>
      <h1>Create your account</h1>
      <form className="stack" onSubmit={submit}>
        <label className="field">
          First name
          <input className="input" autoComplete="given-name" maxLength={80} value={name} onChange={(event) => setName(event.target.value)} />
        </label>
        <label className="field">
          Email
          <input className="input" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <PasswordField label="Password" value={password} onChange={setPassword} autoComplete="new-password" hint="At least 10 characters." />
        {failure && <PageError message={failure} />}
        <button className="btn" type="submit" disabled={busy}>
          {busy ? "Creating your account" : "Create account"}
        </button>
      </form>
      <p className="small muted">
        By creating an account, you agree to the <Link href="/privacy">privacy notice and terms</Link>. Cirrus gives general budgeting information, not financial advice.
      </p>
      <p className="small">
        Already have an account? <Link href="/login">Sign in</Link>
      </p>
    </AuthFrame>
  );
}
