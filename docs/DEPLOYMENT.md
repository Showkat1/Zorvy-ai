# Deploying Zorvy

This is the production runbook for the two-service stack:

| Piece | Host | Domain | What runs there |
|---|---|---|---|
| Web app | Vercel | `app.<domain>` | Next.js 16 (App Router) |
| API | Railway | `api.<domain>` | FastAPI + Alembic migrations |
| Database | Railway Postgres | private | PostgreSQL 18 (`pgvector` not required today) |
| Payments | Razorpay | — | Subscriptions, UPI Autopay, cards, netbanking |

Everything below assumes a real domain you control. **Do not ship on
`*.vercel.app` + `*.railway.app`**: the refresh token is an httpOnly cookie with
`SameSite=Lax`, and those are two different sites, so the browser would drop the
cookie on every refresh. `app.<domain>` and `api.<domain>` share a registrable
domain, which keeps the cookie same-site.

---

## 0. What you need before starting

- A domain (for example `zorvy.ai`).
- A [Railway](https://railway.com) account.
- A [Vercel](https://vercel.com) account.
- A [Razorpay](https://razorpay.com) account with KYC started. Test-mode keys
  work immediately; live keys need KYC approval.
- The repo pushed to GitHub (`Showkat1/Zorvy-ai` today).

No code changes are required to deploy. The only values you add are environment
variables.

---

## 1. API on Railway

### 1.1 Create the project and database

1. **New Project → Deploy from GitHub repo** → pick `Zorvy-ai`.
2. Open the service → **Settings → Source** → set **Root Directory** to `backend`.
   Railway picks up `backend/Dockerfile` automatically.
3. **New → Database → Add PostgreSQL** in the same project. Railway exposes
   `DATABASE_URL` (a `postgresql://` URL) to services in the project.

### 1.2 Environment variables

Add these to the API service (**Variables → Raw editor** is fastest). Replace
`example.com` and the secrets.

```dotenv
ZORVY_ENVIRONMENT=production
ZORVY_DEBUG=false
ZORVY_LOG_LEVEL=INFO
ZORVY_LOG_JSON=true
ZORVY_SECRET_KEY=<48+ random chars: python -c "import secrets; print(secrets.token_urlsafe(48))">

# Railway gives DATABASE_URL; the app needs the asyncpg driver prefix.
ZORVY_DATABASE_URL=postgresql+asyncpg://<user>:<password>@<host>:<port>/<db>
ZORVY_AUTO_CREATE_TABLES=false

ZORVY_FRONTEND_URL=https://app.example.com
ZORVY_CORS_ORIGINS=https://app.example.com
ZORVY_COOKIE_SECURE=true
# Leading dot so the cookie is valid for both app. and api.
ZORVY_COOKIE_DOMAIN=.example.com

# Uploads must live on a mounted volume, not the container filesystem.
ZORVY_UPLOAD_DIR=/uploads
ZORVY_MAX_UPLOAD_SIZE_MB=10
ZORVY_PIPELINE_MODE=background
ZORVY_SEED_KNOWLEDGE_ON_STARTUP=true

ZORVY_LLM_ENABLED=true
ZORVY_LLM_API_KEY=<optional; empty = deterministic engine>
ZORVY_EMBEDDING_PROVIDER=hash
ZORVY_OCR_ENABLED=true

ZORVY_BILLING_CURRENCY=INR
ZORVY_BILLING_TOTAL_COUNT=120
ZORVY_FREE_INVESTIGATIONS_PER_MONTH=5
ZORVY_FREE_DEVICE_SCANS_PER_MONTH=3
ZORVY_PRO_DEVICE_SCANS_PER_MONTH=30
ZORVY_RAZORPAY_KEY_ID=
ZORVY_RAZORPAY_KEY_SECRET=
ZORVY_RAZORPAY_WEBHOOK_SECRET=
ZORVY_RAZORPAY_PLAN_PRO=
ZORVY_RAZORPAY_PLAN_STANDARD=
```

Notes:

- `ZORVY_DATABASE_URL` must start with `postgresql+asyncpg://`. Copy the
  credentials out of Railway's `DATABASE_URL` and swap the scheme.
- The container runs `alembic upgrade head` before starting uvicorn
  (`backend/Dockerfile`), so migrations apply on every deploy. A failed
  migration aborts the deploy instead of serving a half-migrated schema.
- Billing variables can stay empty on the first deploy. The Free plan and the
  pricing page work; checkout returns `503 billing_not_configured` until §3 is
  done.

### 1.3 Volume, port and domain

1. **Settings → Volumes → Add Volume**, mount path `/uploads`.
2. **Settings → Networking → Public Networking → Generate Domain**, then set the
   target port to **8000**.
3. **Custom Domain** → `api.example.com`. Railway prints a CNAME target; create
   that record at your DNS provider.

### 1.4 Smoke test

```bash
curl https://api.example.com/health
curl https://api.example.com/api/v1/billing/plans
```

`/health` should report `"status": "ok"`; `/billing/plans` should list Free, Pro
and Standard with `billing_enabled: false` until §3.

---

## 2. Web app on Vercel

1. **Add New → Project** → import the same GitHub repo.
2. **Root Directory**: `frontend`. Framework preset: Next.js. Build command and
   output are detected (`next build`).
3. **Environment Variables** (Production + Preview):

   ```dotenv
   NEXT_PUBLIC_API_URL=https://api.example.com
   ```

   This value is inlined at build time, so change it before the first build and
   redeploy after any change.
4. **Deploy**, then **Settings → Domains → Add** `app.example.com`. Vercel gives
   you a CNAME (`cname.vercel-dns.com`) — create it at your DNS provider.
5. Wait for both certificates to show **Valid**, then open
   `https://app.example.com`.

### DNS summary

| Name | Type | Value |
|---|---|---|
| `app` | CNAME | Vercel's target (`cname.vercel-dns.com`) |
| `api` | CNAME | Railway's target |

Use `CNAME` records rather than an apex `A` record so the hosts can rotate
addresses. If your DNS provider supports `CNAME` flattening at the apex, you can
also serve the marketing site at the bare domain.

---

## 3. Razorpay subscriptions

### 3.1 Create the plans

Plans are immutable in Razorpay, so they are created once per account (test and
live separately):

```bash
cd backend
# Test mode
ZORVY_RAZORPAY_KEY_ID=rzp_test_xxxxxxxx \
ZORVY_RAZORPAY_KEY_SECRET=xxxxxxxx \
uv run python scripts/setup_razorpay_plans.py
```

The script prints:

```text
ZORVY_RAZORPAY_PLAN_PRO=plan_xxxxxxxx
ZORVY_RAZORPAY_PLAN_STANDARD=plan_xxxxxxxx
```

Re-running reuses a plan that already carries the `zorvy_plan` note, so it is
safe to run twice. Use `--dry-run` to inspect the payloads without calling the
API.

Pricing encoded by the script (change the script and create new plans if you
reprice — existing subscriptions keep their old price):

| Plan | Price | Interval | Limits |
|---|---|---|---|
| Pro | ₹499 | monthly | Unlimited investigations, 30 scans, export |
| Standard | ₹1,999 | monthly | Unlimited investigations and scans, export, API access |

### 3.2 Keys and webhook

1. Razorpay Dashboard → **Account & Settings → API Keys → Generate Key**.
   Copy the **Key ID** and **Key Secret** into Railway.
2. **Account & Settings → Webhooks → Add New Webhook**:
   - URL: `https://api.example.com/api/v1/billing/webhook`
   - Secret: a long random string → `ZORVY_RAZORPAY_WEBHOOK_SECRET`
   - Active events: `subscription.activated`, `subscription.charged`,
     `subscription.cancelled`, `subscription.halted`, `subscription.paused`,
     `subscription.resumed`, `subscription.completed`, `subscription.expired`
3. Redeploy the API so the new variables are live.

The webhook signature is verified with HMAC-SHA256 over the raw body. Handler
state changes are idempotent and ignore stale events for a superseded
subscription, so Razorpay's at-least-once delivery is safe.

### 3.3 End-to-end payment test

With test keys:

1. Register a fresh account on `app.example.com`.
2. Settings → Billing → **Upgrade to Pro**.
3. In the Razorpay modal use UPI success (`success@razorpay`) or card
   `4111 1111 1111 1111`, any future expiry, any CVV.
4. The modal calls `/billing/verify`, the plan flips to Pro, and export plus the
   higher limits unlock immediately.
5. Razorpay Dashboard → Webhooks → check the delivery log returns `200 {"status":"ok"}`.
6. Test cancellation: Settings → Billing → **Cancel plan**. The plan stays active
   until `current_period_end` and `cancel_at_period_end` becomes true.

Switch to live keys only after KYC approval, create live plans with the same
script, and repeat the test with a real ₹1 payment if you want certainty.

---

## 4. Post-deploy verification

| Check | Expected |
|---|---|
| `https://api.example.com/health` | `status: ok`, DB reachable |
| `https://app.example.com` | Landing page with pricing section |
| Register → reload the page | Session survives (refresh cookie works) |
| Sixth investigation on Free | `402 payment_required` with an upgrade prompt |
| Fourth device scan on Free | `402 payment_required` |
| Export on Free | `402 payment_required` |
| Upgrade to Pro | Unlimited investigations, export returns JSON |
| `ZORVY_RAZORPAY_*` empty | Checkout shows "not configured", no crash |

---

## 5. Operations

- **Migrations**: `alembic upgrade head` runs on every API deploy. To run it
  manually: Railway → service → **Command** → `alembic upgrade head`.
- **Backups**: Railway Postgres → enable scheduled backups before real traffic.
- **Logs**: `railway logs` or the Railway Logs tab; JSON logs when
  `ZORVY_LOG_JSON=true`.
- **Retention**: `ZORVY_RETENTION_DAYS` controls stored uploads cleanup via
  `scripts/cleanup.py` (schedule it as a Railway cron if you rely on it).
- **Scaling**: the pipeline runs as an in-process background task
  (`ZORVY_PIPELINE_MODE=background`). One API instance is correct for launch; if
  you scale horizontally, move the pipeline to a queue first, otherwise a
  restarted instance can leave an investigation stuck in `running`.

### Cost at launch (approximate)

| Item | Monthly |
|---|---|
| Railway Hobby (API + Postgres + volume) | $5–15 |
| Vercel Pro (needed for commercial use) | $20 |
| Domain | ~$1–3 |
| Razorpay | 2% + GST per successful payment |
| LLM (optional) | usage-based; empty key = ₹0 |

---

## 6. Rollback

1. Vercel → Deployments → previous deployment → **Promote to Production**.
2. Railway → Deployments → previous deployment → **Redeploy**.
3. Migrations are forward-only. `0003_subscriptions` only adds a table, so
   rolling the API back before that migration has run is safe; rolling back
   after it is also safe because older code ignores the table. Do not hand-edit
   `alembic_version`.
