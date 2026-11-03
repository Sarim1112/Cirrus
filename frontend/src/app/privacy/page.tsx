import type { Metadata } from "next";
import { Wordmark } from "@/components/Brand";

export const metadata: Metadata = { title: "Privacy and terms: Cirrus" };

export default function PrivacyPage() {
  return (
    <main className="prose">
      <Wordmark />
      <h1>Privacy and terms</h1>
      <p className="muted" style={{ marginTop: 8 }}>
        This describes how the Cirrus software handles your data. Whoever runs this copy of Cirrus is responsible for keeping it accurate.
      </p>

      <h2>What Cirrus stores</h2>
      <ul>
        <li>Your email, a hashed version of your password and your settings.</li>
        <li>The transactions in statements you import, including the original statement text. The original file isn&apos;t kept.</li>
        <li>Your budgets, goals and advisor conversation.</li>
      </ul>

      <h2>How AI is used</h2>
      <ul>
        <li>Figures are calculated by Cirrus itself, and a model only helps with wording.</li>
        <li>The default model runs on this Cirrus server through Ollama. No data goes to an outside AI company unless the operator changes that setup.</li>
        <li>Emails, card numbers, phone numbers and long account numbers are masked before text reaches a model.</li>
      </ul>

      <h2>Your control</h2>
      <ul>
        <li>Download everything from Settings at any time.</li>
        <li>Deleting your account permanently removes your data from the live database. Any backups kept by the operator expire on their own schedule.</li>
        <li>Demo data is deleted automatically after 24 hours.</li>
      </ul>

      <h2>What Cirrus doesn&apos;t do</h2>
      <ul>
        <li>It doesn&apos;t connect to your bank or move money.</li>
        <li>It doesn&apos;t sell your data or show ads.</li>
      </ul>

      <h2>Terms</h2>
      <p>
        Cirrus gives general budgeting information, not financial, tax, legal or investment advice. Statement parsing and forecasts can be wrong, so check anything important before relying on it. The
        software is provided as is, without warranty.
      </p>
    </main>
  );
}
