# Architecture

## Services

| Service | Role |
|---|---|
| `web` | Next.js site. Proxies `/api/*` to the API, so the browser only ever talks to one origin. |
| `api` | FastAPI. Authentication, imports, analytics and the advisor. |
| `db` | PostgreSQL. |
| `ollama` | Runs the local model. Optional: everything works without it. |

## Import pipeline

1. **Parse.** The CSV parser detects the encoding, delimiter, header row or headerless layout, date order and amount style. The PDF parser reads text lines, then works out money direction from the running balance, section headings or wording.
2. **Preview.** Parsing runs without saving, and the person checks the result. They can correct the date order or reverse the amounts.
3. **Clean.** Processor prefixes, store numbers, cities and reference codes are removed. Known merchants get a tidy name, and free-text transfer descriptions never become merchant names, which keeps other people's names out.
4. **Categorize.** The person's own corrections win, then built-in patterns. An optional AI pass handles what's left, and its answers are checked against the allowed list.
5. **De-duplicate.** A hash of date, amount, description and the row's occurrence number means two identical coffees on one day are kept, while a re-uploaded statement adds nothing.

## Analytics engine

`backend/app/engine` is pure functions over a list of transactions and a date. It has no database, network or model access, which is what makes it easy to test.

- Money is integer cents. Negative is money out.
- Transfers count as neither income nor spending, and refunds reduce spending.
- Averages use complete months only, so a half-finished month can't skew them.
- "Typical" means the median, so a single large purchase isn't mistaken for a habit.
- Recurring detection groups by merchant and direction, classifies the gaps between charges, then checks that the amounts are stable.
- Unusual purchases use a median-based outlier test, so one large purchase can't hide the next.

### Safe to spend

```
safe = balance - bills before next pay - safety buffer - goal money - held back
```

`held back` looks 31 days ahead, assuming usual spending resumes after payday. If spending the whole amount would leave rent uncovered a few days after payday, the difference is kept back. The breakdown always adds up, and the interface shows it.

## Advisor

For each message (`backend/app/advisor/orchestrator.py`):

1. **Safety check.** Crisis language, illegal requests, prompt injection, investment picks and questions for a licensed professional are handled here, before any model call.
2. **Routing.** Plain rules map common questions to a calculation tool and read the period, amount, category and merchant. Small local models can lose coherence across several tool calls, so common questions don't depend on one.
3. **Calculation.** Each tool returns structured data, a correct written answer, chart definitions and the transactions behind the answer.
4. **Rewording.** If a model is available, it rephrases the answer. Personal details are masked first, and statement data is marked as untrusted.
5. **Verification.** Every figure in the reply must match the tool data, the written answer or the person's own message. Rounding to whole dollars is allowed, and spelled-out amounts and investment recommendations are rejected. A failed reply gets one retry, then the calculated answer is used.

Questions the router can't place go to the model with a read-only tool list, for at most three rounds. The same verifier applies. A general answer such as "what's an emergency fund?" passes only if it cites no figures.

## Adding a model provider

Implement the `ChatProvider` protocol in `backend/app/advisor/providers.py`, then return it from `get_provider()`. If you add a hosted provider, update the privacy notice and Settings text, which currently state that data isn't sent to an outside AI service.
