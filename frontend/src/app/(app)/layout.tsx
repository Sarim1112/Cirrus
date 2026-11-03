"use client";

import {
  ArrowLeftRight,
  CircleEllipsis,
  Flag,
  Gauge,
  LineChart,
  LogOut,
  MessageCircle,
  Settings,
  Sun,
  Upload,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Wordmark } from "@/components/Brand";
import { UserContext } from "@/components/UserContext";
import { ApiError, api, send } from "@/lib/api";
import type { User } from "@/lib/types";

type NavItem = { href: string; label: string; icon: LucideIcon };

const PRIMARY: NavItem[] = [
  { href: "/overview", label: "Overview", icon: Sun },
  { href: "/advisor", label: "Advisor", icon: MessageCircle },
  { href: "/transactions", label: "Transactions", icon: ArrowLeftRight },
  { href: "/plan", label: "Plan", icon: LineChart },
];
const SECONDARY: NavItem[] = [
  { href: "/budgets", label: "Budgets", icon: Gauge },
  { href: "/goals", label: "Goals", icon: Flag },
  { href: "/import", label: "Import", icon: Upload },
  { href: "/settings", label: "Settings", icon: Settings },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [moreOpen, setMoreOpen] = useState(false);

  const refreshUser = useCallback(async () => {
    setUser(await api<User>("/api/auth/me"));
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loading the session is this effect's job
    refreshUser().catch((caught: ApiError) => {
      if (caught.status === 401) router.replace("/login");
      else setFailure(caught.message);
    });
  }, [refreshUser, router]);

  const value = useMemo(() => (user ? { user, refreshUser } : null), [user, refreshUser]);

  async function signOut() {
    await send("/api/auth/logout", "POST").catch(() => undefined);
    router.push("/");
  }

  if (failure) {
    return (
      <div className="prose">
        <div className="form-error" role="alert">
          {failure}
        </div>
      </div>
    );
  }
  if (!user || !value) {
    return (
      <div className="prose">
        <p className="muted" role="status">
          Loading your finances
        </p>
      </div>
    );
  }

  const current = (href: string) => (path === href ? "page" : undefined);
  const inMore = SECONDARY.some((item) => item.href === path);

  return (
    <UserContext.Provider value={value}>
      <div className="app-root">
        {user.is_demo && (
          <div className="demo-bar">
            <span>You&apos;re exploring sample data. It&apos;s deleted after 24 hours.</span>
            <Link href="/register">Create your own account</Link>
          </div>
        )}
        <div className="shell">
          <nav className="rail" aria-label="Main">
            <Wordmark href="/overview" />
            {[...PRIMARY, ...SECONDARY].map(({ href, label, icon: Icon }) => (
              <Link key={href} className="nav-link" href={href} aria-current={current(href)}>
                <Icon size={19} aria-hidden="true" />
                {label}
              </Link>
            ))}
            <div className="rail-spacer" />
            <button className="nav-link" onClick={signOut}>
              <LogOut size={19} aria-hidden="true" />
              {user.is_demo ? "Leave demo" : "Sign out"}
            </button>
          </nav>
          <main className="main">{children}</main>
        </div>
      </div>

      {moreOpen && (
        <div className="more-sheet">
          {SECONDARY.map(({ href, label, icon: Icon }) => (
            <Link key={href} className="nav-link" href={href} aria-current={current(href)} onClick={() => setMoreOpen(false)}>
              <Icon size={19} aria-hidden="true" />
              {label}
            </Link>
          ))}
          <button className="nav-link" onClick={signOut}>
            <LogOut size={19} aria-hidden="true" />
            {user.is_demo ? "Leave demo" : "Sign out"}
          </button>
        </div>
      )}
      <nav className="tabs" aria-label="Main">
        {PRIMARY.map(({ href, label, icon: Icon }) => (
          <Link key={href} href={href} aria-current={current(href)} onClick={() => setMoreOpen(false)}>
            <Icon size={21} aria-hidden="true" />
            {label === "Transactions" ? "Spending" : label}
          </Link>
        ))}
        <button aria-expanded={moreOpen} aria-current={inMore ? "page" : undefined} onClick={() => setMoreOpen(!moreOpen)}>
          <CircleEllipsis size={21} aria-hidden="true" />
          More
        </button>
      </nav>
    </UserContext.Provider>
  );
}
