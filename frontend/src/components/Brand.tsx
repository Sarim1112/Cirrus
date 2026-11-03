import Link from "next/link";

export function Mark({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="#06283D" />
      <path d="M4 23c4-1 6-8 11-8 4 0 5 4 8 4 2 0 4-1 5-3v12H4z" fill="#FDFDFE" />
      <circle cx="23" cy="10" r="3" fill="#E5533D" />
    </svg>
  );
}

export function Wordmark({ href = "/" }: { href?: string }) {
  return (
    <Link className="wordmark" href={href}>
      <Mark />
      Cirrus
    </Link>
  );
}
