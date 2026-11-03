import Link from "next/link";
import { Wordmark } from "@/components/Brand";
import { DemoButton } from "@/components/DemoButton";

const github = process.env.NEXT_PUBLIC_GITHUB_URL;

const QUESTIONS = [
  ["Where can I cut back?", "Ranks your flexible spending against your own better months, and names the merchant to start with."],
  ["Can I afford a $1,500 trip by March?", "Checks your real surplus and goals, keeps a cushion and says what to trim if you fall short."],
  ["What if I halve food delivery?", "Shows the change to your month, your year and your balance over the next 12 months."],
  ["Anything unusual lately?", "Catches double charges, price increases, one-off spikes and subscriptions you may have forgotten."],
];

export default function LandingPage() {
  return (
    <>
      <header className="hero">
        <nav className="land-nav" aria-label="Main">
          <Wordmark />
          <div className="land-nav-links">
            {github && <a href={github}>GitHub</a>}
            <Link href="/login">Sign in</Link>
          </div>
        </nav>
        <div className="hero-grid">
          <div>
            <h1>Know what&apos;s safe to spend.</h1>
            <p className="hero-lead">
              Cirrus reads your bank statements, forecasts your balance and gives budget tips you can trace back to real transactions.
            </p>
            <div className="hero-actions">
              <DemoButton />
              <Link className="text" href="/register">
                Create an account
              </Link>
            </div>
            <p className="small" style={{ marginTop: 12 }}>
              The demo uses sample data and needs no sign-up.
            </p>
          </div>
          <div className="hero-chat" aria-label="An example conversation with sample figures">
            <p className="q">What&apos;s safe to spend?</p>
            <div className="a">
              You have $612 safe to spend until payday on Friday. That sets aside $1,725 for rent, $96 for bills and a $100 buffer.
              <span className="proof">Based on 14 transactions</span>
            </div>
            <p className="small">Sample figures</p>
          </div>
        </div>
        <svg className="hero-horizon" viewBox="0 0 1440 190" preserveAspectRatio="none" aria-hidden="true">
          <path d="M0 150C160 146 230 58 390 66c150 8 190 92 340 98 150 5 200-122 350-122 140 0 210 62 360 54v94H0Z" fill="#FDFDFE" />
        </svg>
      </header>

      <main>
        <section className="land-section" aria-labelledby="how">
          <h2 id="how">From statement to plan in three steps</h2>
          <ol className="how">
            <li>
              <h3>Upload a statement</h3>
              <p>Drop in a CSV or PDF. Cirrus cleans merchant names, sorts categories and finds your bills and paydays. You check a preview before anything is saved.</p>
            </li>
            <li>
              <h3>See where you&apos;re heading</h3>
              <p>A day-by-day forecast shows your expected balance, your lowest point and how much is free before your next pay.</p>
            </li>
            <li>
              <h3>Ask anything</h3>
              <p>Get answers in plain language, with charts and the exact transactions behind them.</p>
            </li>
          </ol>
        </section>

        <section className="land-section" aria-labelledby="ask" style={{ paddingTop: 0 }}>
          <h2 id="ask">Questions it can answer</h2>
          <ul className="qa-grid">
            {QUESTIONS.map(([question, answer]) => (
              <li key={question}>
                <strong>{question}</strong>
                <span className="muted">{answer}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="promise" aria-labelledby="trust">
          <div className="land-section">
            <h2 id="trust">The numbers come from your data, not from a guess</h2>
            <ul>
              <li>Cirrus calculates every figure in code. The AI only helps with wording, and any reply with a figure it can&apos;t verify is thrown out.</li>
              <li>The default model runs locally through Ollama, so your statements don&apos;t go to an outside AI company.</li>
              <li>It never tells you what to invest in, and it can&apos;t move your money.</li>
              <li>
                Download or permanently delete your data whenever you like. <Link href="/privacy">How your data is handled</Link>
              </li>
            </ul>
          </div>
        </section>
      </main>

      <footer className="footer">
        <span>Cirrus gives general budgeting information, not financial, tax or legal advice.</span>
        <Link href="/privacy">Privacy and terms</Link>
      </footer>
    </>
  );
}
