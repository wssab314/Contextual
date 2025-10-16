Here’s a complete, polished **README.md** you can drop into your repo. It keeps the product story crisp, adds a clear Quick Start, environment/config docs, ops commands, smoke test, troubleshooting, and links to your Chinese docs.

---

# Contextual

<div align="right">
  <a href="docs/README.zh-CN.md">🇨🇳 中文文档</a>
</div>

> **AI-powered dev context manager.**
> Lives in DingTalk / Slack / Microsoft Teams. Links commits ⇄ Jira with one click.

---

## Table of Contents

* [What is Contextual?](#what-is-contextual)
* [Why it matters](#why-it-matters)
* [How it works](#how-it-works)
* [Architecture (Phase 2 MVP)](#architecture-phase-2-mvp)
* [Repository Layout](#repository-layout)
* [Quick Start (Hello-Flow)](#quick-start-hello-flow)
* [Configuration](#configuration)
* [Run & Operate](#run--operate)
* [Smoke Test](#smoke-test)
* [Troubleshooting](#troubleshooting)
* [Roadmap](#roadmap)
* [Contributing](#contributing)
* [License](#license)

---

## What is Contextual?

**Contextual** is an AI-powered bot that acts as your development team’s automated knowledge manager. It lives where your team collaborates—**DingTalk, Slack, Microsoft Teams**—and silently closes the gap between your **codebase** and your **project management** system.

## Why it matters

In fast-moving teams, the crucial link between a code change and the business requirement it fulfills gets lost. This “context gap” causes:

* **Slow onboarding** — New engineers struggle to reconstruct the “why.”
* **Painful maintenance** — Debugging devolves into ticket archaeology and pinging colleagues.
* **Ineffective code reviews** — Reviewers lack the story behind changes.

## How it works

1. **Analyze** — Watches your Git repo for new commits.
2. **Understand** — Uses an LLM to embed the code `diff` + `commit message`.
3. **Recommend** — Searches Jira and picks the **single most relevant** issue.
4. **Interact** — Sends a light prompt in chat: *“Likely JIRA-123. Correct?”*
5. **Link** — One click **[✅ Yes, link it]** creates a permanent, queryable link.
   Contextual learns from feedback and becomes smarter over time.

---

## Architecture (Phase 2 MVP)

Message-driven microservices; async and resilient.

* **webhook** — FastAPI service (port **8001**)
  Receives Git webhooks, validates `X-Hub-Signature-256`, publishes to MQ topic **`git_commit_raw`**.

* **core** — FastAPI service (port **8000**)
  Consumes events → (MVP stub) selects top-1 Jira key → sends DingTalk **ActionCard** → logs to `notifications`.
  *Behavior note:* card text is auto-prefixed with `DINGTALK_KEYWORD` when configured to satisfy DingTalk’s keyword policy.

* **callback** — FastAPI service (port **8003**)
  Receives ActionCard button clicks → writes to `interaction_log`.

* **Infra**

  * **PostgreSQL** (+ `pgvector` for future semantic search)
  * **RabbitMQ** (decoupling, backpressure)
  * **Redis** (optional: caching/rate-limits)

> Current MVP sends a fixed recommendation (`DEMO-1`) to validate the end-to-end loop.

---

## Repository Layout

```
services/
  core/       # main orchestration, sends DingTalk ActionCard
  webhook/    # receives Git webhooks, validates, publishes to MQ
  callback/   # receives DingTalk interactions, writes to DB
infra/
  migrations/ # SQL migrations (e.g., notifications, interaction_log)
scripts/
  smoke.sh    # one-click health+send+simulate test
docs/
  README.zh-CN.md  # Chinese docs
  RUNBOOK.md       # Ops runbook (quick tunnel changes, self-checks)
docker-compose.yml
Makefile
.env.example
```

---

## Quick Start (Hello-Flow)

Goal: **`git push` → DingTalk card → click ✅ → DB updated.**

### Prerequisites

* Docker Desktop (with Compose), Git, Python 3
* DingTalk **Custom Bot**

  * If using **加签**, keep the `DINGTALK_SECRET`.
  * If using **Keyword**, set something like `contextual` (we auto-prefix messages).
* Two quick tunnels (Cloudflare or ngrok):

  * Tunnel to **localhost:8003** → becomes `PUBLIC_BASE_URL` (callback buttons)
  * Tunnel to **localhost:8001** → GitHub Webhook **Payload URL**

### 1) Configure environment

```bash
cp .env.example .env
# Edit .env:
# - DINGTALK_WEBHOOK_URL=...
# - DINGTALK_SECRET=...                # if signing is enabled
# - DINGTALK_KEYWORD=contextual        # must match your DingTalk bot keyword
# - PUBLIC_BASE_URL=https://<tunnel-8003>
# - GIT_WEBHOOK_SECRET=<your-hmac-secret>
```

### 2) Boot services

```bash
docker compose up -d
```

### 3) Expose callback (8003) and set `PUBLIC_BASE_URL`

```bash
cloudflared tunnel --url http://localhost:8003
# copy the https://<xxx>.trycloudflare.com
make set-callback NEW=https://<xxx>.trycloudflare.com
```

### 4) Configure GitHub Webhook

In your repo: **Settings → Webhooks → Add webhook**

* **Payload URL**: `https://<tunnel-for-8001>/ingest/git`
* **Content type**: `application/json`
* **Secret**: same as `GIT_WEBHOOK_SECRET` in `.env`
* **Events**: `Just the push event` → Save

### 5) One-command smoke test

```bash
make smoke
# Expected: webhook+callback health OK; DingTalk receives a "smoke-check" text; a new ActionCard appears.
```

### 6) Verify the loop

* Click **✅** on the card.
* Inspect DB:

```bash
make db-last
# Expected: notifications.clicked_at has a timestamp; interaction_log has a new row.
```

---

## Configuration

| Key                    | Example                                                 | Notes                                                                                          |
| ---------------------- | ------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `GIT_WEBHOOK_SECRET`   | `changeme-github-secret`                                | HMAC secret for `X-Hub-Signature-256`. Must match GitHub Webhook.                              |
| `DINGTALK_WEBHOOK_URL` | `https://oapi.dingtalk.com/robot/send?access_token=...` | DingTalk custom bot URL.                                                                       |
| `DINGTALK_SECRET`      | `SEC...`                                                | DingTalk signing secret (if **加签** enabled).                                                   |
| `DINGTALK_KEYWORD`     | `contextual`                                            | If your bot enforces **Keyword**, this word must be included. We auto-prefix messages with it. |
| `PUBLIC_BASE_URL`      | `https://xxx.trycloudflare.com`                         | Public base URL for **callback** (8003). Buttons use this.                                     |
| `RELAY_URL` (optional) | `http://host.docker.internal:9000/send`                 | If direct access to DingTalk is blocked, point core to your relay.                             |
| `POSTGRES_*`           | `postgres/contextual`                                   | DB connection (Compose defaults).                                                              |
| `RABBITMQ_*`           | `guest/guest`                                           | MQ creds (Compose defaults).                                                                   |

> `.env` is ignored by git. Use `.env.example` as your safe template.

---

## Run & Operate

Common tasks via **Makefile**:

```bash
make up            # start all services
make down          # stop all services
make logs-core     # tail core logs
make logs-webhook  # tail webhook logs
make logs-callback # tail callback logs
make restart-core  # recreate core to reload env
make rebuild-core  # rebuild core image and start
make set-callback NEW=https://X.trycloudflare.com   # update PUBLIC_BASE_URL and restart core
make mq            # RabbitMQ queues
make db-last       # recent notifications & interaction logs
```

More ops notes in **docs/RUNBOOK.md** (quick tunnel swaps, self-checks, common errors).

---

## Smoke Test

We ship `scripts/smoke.sh` for a full-path self-check:

1. Health check: `/health` on **webhook** and **callback**
2. Send DingTalk **text** (keyword-aware)
3. Simulate a Git `push` to `/ingest/git`

Run:

```bash
./scripts/smoke.sh
```

---

## Troubleshooting

* **No card in DingTalk, but `delivered_at` exists**
  Your bot likely enforces **Keyword**. Ensure `.env` has `DINGTALK_KEYWORD` that matches bot settings.
  The core service auto-prefixes the keyword; DingTalk should return `{"errcode":0}`.

* **GitHub Webhook shows 404**
  Payload URL must include path: **`/ingest/git`** (not `/`).

* **Webhook returns 401**
  Signature mismatch. `GIT_WEBHOOK_SECRET` must match GitHub’s Webhook Secret.

* **Callback opens but DB not updated**
  Old cards still point to the **old** `PUBLIC_BASE_URL`. After changing tunnels, update `.env`, run `make set-callback NEW=...`, then send a **new** card.

* **RabbitMQ `unacked` grows**
  Typically a DB write issue. Current core acks **after successful send**; DB failures log warnings and won’t block consumption.

* **Containers can’t reach `oapi.dingtalk.com` (China mainland networks)**
  Prefer direct access: clear proxy envs in the container, set `NO_PROXY=.dingtalk.com`, use domestic DNS in Compose.
  As a fallback, set up a local/edge **relay** and configure `RELAY_URL`.

---

## Roadmap

* 🔍 Replace MVP stub with real **embedding + vector search** against Jira (`pgvector` now; optional Weaviate/Milvus later).
* 🧠 Online learning from `interaction_log` to improve ranking.
* 🧩 Slack/Teams parity with the DingTalk flow.
* 📊 Basic dashboard: deliveries, clicks, latency, failure rates.
* 🔐 Secret management (Vault/K8s Secrets) & per-tenant configs.

---

## Contributing

PRs welcome! Please:

* Keep changes small and observable (add meaningful logs).
* Update **docs/RUNBOOK.md** and **README** when user flows change.
* Don’t commit secrets; `.env` is ignored.

---

## License

MIT © wssab314

---

*Also available in Chinese: [docs/README.zh-CN.md](docs/README.zh-CN.md)*
