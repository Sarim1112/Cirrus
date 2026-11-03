# Security

## Reporting a problem

Please report vulnerabilities privately through GitHub's **Report a vulnerability** option on the Security tab, not in a public issue.

## What's in place

**Accounts**

- Passwords are hashed with Argon2id. Login timing and error messages don't reveal which emails have accounts.
- Sessions are random tokens, and only their SHA-256 hash is stored. Cookies are `HttpOnly` and `SameSite=Lax`, and `Secure` in production.
- Password reset links are single-use, expire in an hour and end all existing sessions.
- Login, registration, reset, demo, import and chat requests are rate limited.

**Data**

- Every query is scoped to the signed-in user, and the test suite tries to cross that boundary through each route.
- Deleting an account cascades to all of that user's rows.
- Uploaded files are parsed in memory and not kept. Size, row and page limits apply.
- CSV exports neutralise spreadsheet formulas.
- Writes from other origins are rejected, and the site sends a Content Security Policy and related headers.

**AI**

- The model has read-only tools, and it can't change data or move money.
- Emails, card numbers, phone numbers, ID-like numbers, postal codes and long digit runs are masked before text reaches a model.
- Statement text is treated as untrusted, because a merchant name can contain instructions. Figures in a reply must match the calculations, whatever the model was told.
- Investment picks, and requests for help with tax evasion or fraud, are declined.

## What isn't in place

Know these limits before you store real people's data:

- **The database isn't encrypted by the app.** Use encrypted disks and encrypted backups.
- **Email addresses aren't verified**, and there's no two-factor authentication.
- **Rate limits are per process.** If you run several API workers or machines, add a shared limiter at the proxy.
- **The Content Security Policy allows inline scripts and styles**, which Next.js needs without a nonce setup.
- **The masking is pattern based.** It catches common formats, not every possible personal detail.
- **No independent security audit has been done.**
