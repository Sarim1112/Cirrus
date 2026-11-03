# Deployment

## What it costs

The model is free, but something has to run it. Pick the setup that suits you:

| Setup | What you need | Advisor |
|---|---|---|
| **Built-in answers** | A small server (about 1 GB RAM) with `CIRRUS_AI_ENABLED=false` | Correct figures in plainer wording |
| **Local model on a CPU** | A server with at least 8 GB RAM | AI wording, with replies that can take a while |
| **Local model on a GPU** | A GPU server | AI wording, faster, but the most expensive option |

For a public portfolio site, built-in answers are the cheapest way to stay online. Each visitor can still run the full AI version themselves with Docker. When the shared model is busy, Cirrus answers without it instead of making people queue.

## Production with Docker Compose

Point a domain at your server, then:

```bash
cp .env.example .env
```

In `.env`, set:

```bash
POSTGRES_PASSWORD=a-long-random-password
PUBLIC_URL=https://cirrus.example.com
DOMAIN=cirrus.example.com
```

Then start it. Caddy obtains the HTTPS certificate automatically.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

To leave out the model on a small server:

```bash
CIRRUS_AI_ENABLED=false docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d db api web caddy
```

## Password reset email

Reset links need an email provider. Set `CIRRUS_SMTP_HOST`, `CIRRUS_SMTP_PORT`, `CIRRUS_SMTP_USERNAME`, `CIRRUS_SMTP_PASSWORD` and `CIRRUS_SMTP_FROM`. Without them, reset emails aren't sent: production logs an error, and development prints the link to the API log.

## Launch checklist

Do these before real people upload real statements:

- [ ] HTTPS is working, and `CIRRUS_ENV=production` is set. The API refuses to start with insecure cookies or the default database password.
- [ ] A strong `POSTGRES_PASSWORD` is set.
- [ ] The database disk is encrypted, and backups are encrypted, tested and have a retention period.
- [ ] Email is configured and a password reset has been tested.
- [ ] `/privacy` has been reviewed, and matches how you run the service, including your contact details and backup retention.
- [ ] You've checked the privacy law that applies to you. In Canada, that's usually PIPEDA. If you're unsure, get advice from a lawyer.
- [ ] Logs and uptime are monitored, and you know how to respond to a data breach.
- [ ] You've read [SECURITY.md](../SECURITY.md), including what isn't in place yet.
- [ ] `CIRRUS_DOCS_ENABLED=false` is set, unless you want the API documentation to be public.

## Scaling

The rate limiter and the model's concurrency limit live in the API process. Run one API worker, or add a shared limiter at the proxy before you scale out.
