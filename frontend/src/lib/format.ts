export function money(cents: number, currency = "CAD", whole = false): string {
  const showCents = !whole && cents % 100 !== 0;
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency,
    minimumFractionDigits: showCents ? 2 : 0,
    maximumFractionDigits: showCents ? 2 : 0,
  }).format(cents / 100);
}

function parseDay(iso: string): Date {
  const [year, month, day] = iso.slice(0, 10).split("-").map(Number);
  return new Date(year, month - 1, day);
}

export function shortDate(iso: string): string {
  return parseDay(iso).toLocaleDateString("en-CA", { month: "short", day: "numeric" });
}

export function longDate(iso: string): string {
  return parseDay(iso).toLocaleDateString("en-CA", { month: "long", day: "numeric", year: "numeric" });
}

export function monthLabel(key: string): string {
  return parseDay(`${key}-01`).toLocaleDateString("en-CA", { month: "short" });
}

export function monthYear(iso: string): string {
  return parseDay(iso.length === 7 ? `${iso}-01` : iso).toLocaleDateString("en-CA", {
    month: "long",
    year: "numeric",
  });
}

/** Read a dollar amount typed by a person. Returns cents, or null if it isn't a number. */
export function parseDollars(value: string): number | null {
  const cleaned = value.replace(/[$,\s]/g, "");
  if (!/^-?\d+(\.\d{1,2})?$/.test(cleaned)) return null;
  return Math.round(parseFloat(cleaned) * 100);
}
