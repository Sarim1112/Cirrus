"use client";

import { CheckCircle2, SendHorizontal, Trash2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ChatChart } from "@/components/charts";
import { PageError } from "@/components/ui";
import { useMoney } from "@/components/UserContext";
import { ApiError, send, useFetch } from "@/lib/api";
import { shortDate } from "@/lib/format";
import type { ChatMessage, Evidence } from "@/lib/types";

type Status = { mode: "local_ai" | "built_in"; model: string | null; starters: string[] };

function ReplyText({ text }: { text: string }) {
  const blocks: React.ReactNode[] = [];
  let items: string[] = [];
  const flush = () => {
    if (items.length) {
      blocks.push(
        <ul key={blocks.length}>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>,
      );
      items = [];
    }
  };
  for (const line of text.split("\n")) {
    if (/^\s*[-*•]\s+/.test(line)) {
      items.push(line.replace(/^\s*[-*•]\s+/, ""));
    } else if (line.trim()) {
      flush();
      blocks.push(<p key={blocks.length}>{line}</p>);
    }
  }
  flush();
  return <div className="reply-text">{blocks}</div>;
}

function EvidenceBlock({ evidence }: { evidence: Evidence }) {
  const money = useMoney();
  const count = evidence.total;
  return (
    <details className="evidence">
      <summary>
        Based on {count} {count === 1 ? "transaction" : "transactions"}
      </summary>
      <ul className="evidence-list">
        {evidence.items.map((item) => (
          <li key={item.id}>
            <span className="muted">{shortDate(item.date)}</span>
            <span>{item.merchant}</span>
            <strong>{money(item.amount_cents)}</strong>
          </li>
        ))}
      </ul>
      <Link className="small" href={evidence.href}>
        Open in Transactions
      </Link>
    </details>
  );
}

function Reply({ message, onAsk, latest }: { message: ChatMessage; onAsk: (question: string) => void; latest: boolean }) {
  const { meta } = message;
  return (
    <article className="reply">
      <ReplyText text={message.content} />
      {meta.charts?.map((chart) => <ChatChart key={chart.title} spec={chart} />)}
      {meta.evidence?.map((evidence) => <EvidenceBlock key={evidence.label} evidence={evidence} />)}
      {meta.tools_used && meta.tools_used.length > 0 && (
        <div className="reply-foot">
          <CheckCircle2 size={14} aria-hidden="true" />
          <span>Figures calculated from your transactions{meta.mode === "local_ai" ? ", worded by your local AI" : ""}.</span>
        </div>
      )}
      {meta.note && <p className="small muted">{meta.note}</p>}
      {latest && meta.suggestions && meta.suggestions.length > 0 && (
        <div className="chips">
          {meta.suggestions.map((question) => (
            <button className="chip" key={question} onClick={() => onAsk(question)}>
              {question}
            </button>
          ))}
        </div>
      )}
    </article>
  );
}

export default function AdvisorPage() {
  const { data: status } = useFetch<Status>("/api/chat/status");
  const { data: history, error, reload } = useFetch<{ messages: ChatMessage[] }>("/api/chat/messages");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [progress, setProgress] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- server history seeds the local list
    if (history) setMessages(history.messages);
  }, [history]);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages, progress]);

  const ask = useCallback(
    async (text: string) => {
      const question = text.trim();
      // Wait for saved history, so that it can't arrive late and replace this question.
      if (!question || progress || !history) return;
      setDraft("");
      setFailure(null);
      setProgress("Checking your transactions");
      setMessages((rows) => [
        ...rows,
        { id: `pending-${rows.length}`, role: "user", content: question, meta: {}, created_at: new Date().toISOString() },
      ]);
      try {
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: question }),
        });
        if (!response.ok || !response.body) {
          const body = await response.json().catch(() => null);
          throw new ApiError(body?.detail ?? "The advisor couldn't answer. Try again.", response.status);
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop() ?? "";
          for (const part of parts) {
            const name = part.match(/^event: (.+)$/m)?.[1];
            const payload = part.match(/^data: (.+)$/m)?.[1];
            if (!payload) continue;
            const parsed = JSON.parse(payload);
            if (name === "status") setProgress(parsed.text);
            if (name === "final") setMessages((rows) => [...rows, parsed as ChatMessage]);
          }
        }
      } catch (caught) {
        setFailure((caught as Error).message);
      } finally {
        setProgress(null);
      }
    },
    [progress, history],
  );

  async function clearChat() {
    await send("/api/chat/messages", "DELETE");
    setMessages([]);
  }

  const lastAssistant = [...messages].reverse().find((message) => message.role === "assistant")?.id;

  return (
    <div className="chat">
      <header className="chat-head">
        <div>
          <h1 style={{ fontSize: "1.35rem" }}>Advisor</h1>
          <p className="small muted">{status?.mode === "local_ai" ? `Using ${status.model} on your server` : "Using built-in answers"}</p>
        </div>
        {messages.length > 0 && (
          <button className="icon-btn ghost" onClick={clearChat} aria-label="Clear this conversation" title="Clear this conversation">
            <Trash2 size={18} />
          </button>
        )}
      </header>

      <div className="chat-scroll">
        <div className="chat-column" aria-live="polite">
          {error && <PageError message={error} onRetry={reload} />}
          {history && messages.length === 0 && (
            <div className="stack">
              <h2 style={{ fontSize: "1.8rem", maxWidth: "20ch" }}>What would you like to know about your money?</h2>
              <p className="muted">Every figure comes from your own transactions, and you can open the ones behind each answer.</p>
              <div className="chips">
                {status?.starters.map((question) => (
                  <button className="chip" key={question} onClick={() => ask(question)}>
                    {question}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((message) =>
            message.role === "user" ? (
              <div className="bubble-user" key={message.id}>
                {message.content}
              </div>
            ) : (
              <Reply key={message.id} message={message} onAsk={ask} latest={message.id === lastAssistant && !progress} />
            ),
          )}
          {progress && (
            <div className="typing" role="status">
              <i />
              {progress}
            </div>
          )}
          {failure && <PageError message={failure} />}
          <div ref={end} />
        </div>
      </div>

      <div className="composer">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void ask(draft);
          }}
        >
          <label className="sr-only" htmlFor="question">
            Ask about your money
          </label>
          <input
            id="question"
            className="input"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Ask about your money"
            maxLength={1000}
            autoComplete="off"
            disabled={!history && !error}
          />
          <button className="icon-btn" type="submit" disabled={!draft.trim() || Boolean(progress) || !history} aria-label="Send">
            <SendHorizontal size={19} />
          </button>
        </form>
        <p className="composer-note">Cirrus gives general budgeting information, not financial, tax or legal advice.</p>
      </div>
    </div>
  );
}
