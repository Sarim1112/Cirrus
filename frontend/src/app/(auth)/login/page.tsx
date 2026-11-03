"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuthFrame } from "@/components/AuthFrame";
import { DemoButton } from "@/components/DemoButton";
import { PageError, PasswordField } from "@/components/ui";
import { send } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFailure(null);
    try {
      await send("/api/auth/login", "POST", { email, password });
      router.push("/overview");
    } catch (caught) {
      setFailure((caught as Error).message);
      setBusy(false);
    }
  }

  return (
    <AuthFrame>
      <h1>Sign in</h1>
      <form className="stack" onSubmit={submit}>
        <label className="field">
          Email
          <input className="input" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <PasswordField label="Password" value={password} onChange={setPassword} autoComplete="current-password" />
        {failure && <PageError message={failure} />}
        <button className="btn" type="submit" disabled={busy}>
          {busy ? "Signing in" : "Sign in"}
        </button>
      </form>
      <p className="small">
        <Link href="/forgot-password">Forgot your password?</Link>
      </p>
      <p className="small muted">
        New here? <Link href="/register">Create an account</Link>, or explore with sample data first.
      </p>
      <DemoButton className="btn quiet" />
    </AuthFrame>
  );
}
