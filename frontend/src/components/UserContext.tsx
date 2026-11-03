"use client";

import { createContext, useContext } from "react";
import { money as formatMoney } from "@/lib/format";
import type { User } from "@/lib/types";

type Value = { user: User; refreshUser: () => Promise<void> };

export const UserContext = createContext<Value | null>(null);

export function useUser(): Value {
  const value = useContext(UserContext);
  if (!value) throw new Error("useUser must be used inside the signed-in layout");
  return value;
}

/** A money formatter that already knows the signed-in person's currency. */
export function useMoney() {
  const { user } = useUser();
  return (cents: number, whole = false) => formatMoney(cents, user.currency, whole);
}
