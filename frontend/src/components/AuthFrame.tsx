import { Wordmark } from "./Brand";

export function AuthFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="auth">
      <div className="auth-sky">
        <Wordmark />
        <blockquote>See what&apos;s safe to spend before you spend it.</blockquote>
        <svg viewBox="0 0 600 180" preserveAspectRatio="none" style={{ width: "100%", height: 130, display: "block" }} aria-hidden="true">
          <path d="M0 120C70 118 110 62 180 66s90 70 170 66 90-84 150-82 80 34 100 34v96H0Z" fill="#FDFDFE" />
          <circle cx="295" cy="112" r="8" fill="#E5533D" stroke="#FDFDFE" strokeWidth="3" />
        </svg>
      </div>
      <main className="auth-form">
        <div className="auth-card">{children}</div>
      </main>
    </div>
  );
}
