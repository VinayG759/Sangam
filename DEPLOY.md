# Deploying Sangam

Three free-tier services: **Supabase** (Postgres + pgvector), **Render** (API, Docker), **Vercel**
(dashboard). Each step below is done in that service's web dashboard.

## 1. Database — Supabase

Use a Postgres database with the `vector` extension available (Supabase has it). The first deploy's
migration creates every table and enables the extension.

Copy the **Session pooler** connection string (Project → Connect). It becomes `DATABASE_URL`.

> Sangam v2 uses a new schema. Point it at an **empty** database — a new Supabase project, or one whose
> old tables you no longer need. Do not point it at a database holding data you want to keep.

## 2. API — Render

Web service, **Docker** runtime, root directory `backend`, health check path `/health`.

Environment variables (see `backend/.env.example` for what each one does):

| Variable | Value |
|---|---|
| `DATABASE_URL` | Supabase connection string |
| `ACTIVE_COUNTRY_PACK` | `india` |
| `ALLOWED_ORIGINS` | your Vercel URL, e.g. `https://sangam.vercel.app` |
| `ADMIN_TOKEN` | a long random value (`python -c "import secrets; print(secrets.token_urlsafe(32))"`) |
| `REPORTER_HASH_PEPPER` | a long random value — set once, never change |
| `GEMINI_API_KEY` | AI Studio key |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` | bot token; a secret you choose |
| `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET` | from the Meta app |
| `CONTACT_ENCRYPTION_KEY` | encrypts citizens' chat IDs for status updates (leave empty to store none) |
| `PUBLIC_APP_URL` | your Vercel URL, for tracking links in updates |
| `WHATSAPP_NOTIFY_TEMPLATE` | name of the approved WhatsApp template (optional, see below) |
| `SEED_DEMO` | `true` for the first deploy only (loads synthetic demo reports), then `false` |

On every start the container runs migrations, loads the country pack, and starts the API.

## 3. Dashboard — Vercel

Project root `frontend`, framework Vite. Environment variable `VITE_API_URL` = the Render URL.
`frontend/vercel.json` makes page addresses like `/priorities/12` work on refresh.

## 4. Connect the channels

**Telegram** — register the webhook with the secret (Telegram then includes it on every update):

```
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=<RENDER_URL>/api/v1/webhooks/telegram&secret_token=<TELEGRAM_WEBHOOK_SECRET>
```

**WhatsApp** — in the Meta app, set the webhook URL to `<RENDER_URL>/api/v1/webhooks/whatsapp` with your
`WHATSAPP_VERIFY_TOKEN`, and subscribe to `messages`.

**WhatsApp status updates (optional)** — WhatsApp only allows free-text messages within 24 hours of the
citizen's last message, so later updates need a template approved by Meta. In WhatsApp Manager create a
*Utility* template, e.g. `report_update`, body: `Update on your report {{1}}: {{2}}`. Once approved, set
`WHATSAPP_NOTIFY_TEMPLATE=report_update`. Until then, Telegram users get updates and WhatsApp users can
use the tracking page.

## 5. First analysis run

```bash
curl -X POST -H "Authorization: Bearer <ADMIN_TOKEN>" <RENDER_URL>/api/v1/admin/runs
curl -H "Authorization: Bearer <ADMIN_TOKEN>" <RENDER_URL>/api/v1/admin/runs     # wait for "complete"
```

The run writes AI summaries for the top 15 priorities, pausing between calls to stay inside Gemini's
free-tier rate limit, so it takes about two minutes.

## 6. Verify

```bash
cd backend && python -m scripts.smoke_test <RENDER_URL>
```

Then send one real message on Telegram and one on WhatsApp and check they appear under
`/track/<tracking id>`.

## Keep it awake

`.github/workflows/keepalive.yml` pings the API every 12 hours (Render sleeps after 15 minutes idle;
Supabase pauses after 7 days). Add repository secrets `SANGAM_API_URL` and, to also re-run the analysis,
`SANGAM_ADMIN_TOKEN`.

## Rolling back

Render → the service → Deploys → redeploy the previous one. Migrations only ever add, so the previous
version still works against the newer schema.
