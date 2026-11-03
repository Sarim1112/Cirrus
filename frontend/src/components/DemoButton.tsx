"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { send } from "@/lib/api";

export function DemoButton({ className = "btn solid-ink", label = "Try the demo" }: { className?: string; label?: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      await send("/api/auth/demo", "POST");
      router.push("/overview");
    } catch (caught) {
      setError((caught as Error).message);
      setBusy(false);
    }
  }

  return (
    <>
      <button className={className} onClick={start} disabled={busy}>
        {busy ? "Loading sample data" : label}
      </button>
      {error && (
        <span role="alert" className="small">
          {error}
        </span>
      )}
    </>
  );
}
