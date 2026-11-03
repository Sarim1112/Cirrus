"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AuthFrame } from "@/components/AuthFrame";
import { PageError, PasswordField } from "@/components/ui";
import { send } from "@/lib/api";

function ResetForm() {
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setFailure(null);
    try {
      await send("/api/auth/reset-password", "POST", { token, password });
      setDone(true);
    } catch (caught) {
      setFailure((caught as Error).message);
    }
  }

  if (done) {
    return (
      <>
        <p className="form-ok" role="status">
          Password changed.
        </p>
        <Link className="btn" href="/login">
          Sign in
        </Link>
      </>
    );
  }
  return (
    <form className="stack" onSubmit={submit}>
      <PasswordField label="New password" value={password} onChange={setPassword} autoComplete="new-password" hint="At least 10 characters." />
      {failure && <PageError message={failure} />}
      <button className="btn" type="submit">
        Change password
      </button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <AuthFrame>
      <h1>Choose a new password</h1>
      <Suspense>
        <ResetForm />
      </Suspense>
    </AuthFrame>
  );
}
