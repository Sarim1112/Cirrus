import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Cirrus: know what's safe to spend",
  description:
    "A personal finance advisor that reads your statements, forecasts your balance and gives budget tips you can trace back to real transactions.",
};

export const viewport: Viewport = {
  themeColor: "#0099FF",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
