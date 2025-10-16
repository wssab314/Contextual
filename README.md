# Contextual

> **AI-powered context linker for your commits ↔ Jira.**  
> Runs beside your team (DingTalk first; Slack/Teams next), reads commit intent, recommends the most relevant Jira issue, and lets engineers confirm with one click.

[中文文档 »](docs/README.zh-CN.md)

---

## What’s in the M1 (Phase 2 MVP)
- **Git Webhook → MQ ingest**: `/ingest/git` verifies `X-Hub-Signature-256` and enqueues `git_commit_raw`.
- **Jira data ingestion**: projects/issues synced into Postgres (`jira_projects`, `jira_issues`, `jira_sync_state`).
- **Semantic search (pgvector)**: Embeds Jira issues with an embedding model (LM Studio / Qwen3-Embedding-0.6B-GGUF).
- **Top-K recommendation**: Build a query from commit message + files; return Top-K with cosine similarity.
- **DingTalk ActionCard**: Top-1 + candidates in buttons; one-click confirm/choose.
- **Feedback loop**:
  - `interaction_log` records confirmation/correction.
  - `notifications.clicked_at` tracks delivery/interaction.
  - `commit_links` upserts the **final** mapping `commit → jira_key`.
- **Noise suppression**: `RECO_MIN_SCORE` drops low-confidence candidates (no card sent).

---

## Quickstart

### 0) Prereqs
- Docker / Docker Compose
- DingTalk **custom bot** (webhook + optional keyword + secret)
- Jira Cloud project & API token
- LM Studio (for local embeddings) running at `http://localhost:1234` with model **Qwen3-Embedding-0.6B-GGUF** (dim **1024**)

### 1) Configure `.env`
Create a `.env` in project root (example values):

```ini
# Git webhook
GIT_WEBHOOK_SECRET=replace_me_github_secret

# DingTalk
DINGTALK_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=XXXXX
DINGTALK_SECRET=SECXXXXXXXXXXXX
# If your bot requires a keyword, set it (optional)
# DINGTALK_KEYWORD=[Contextual]

# Public callback base (trycloudflare quick tunnel)
PUBLIC_BASE_URL=https://<your-subdomain>.trycloudflare.com

# Postgres
POSTGRES_HOST=postgres
POSTGRES_DB=contextual
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# Jira (for sync jobs)
JIRA_BASE=https://your-domain.atlassian.net
JIRA_EMAIL=you@example.com
JIRA_TOKEN=your_api_token
JIRA_PROJECT_KEY=SCRUM

# Embedding (LM Studio)
EMBED_API_BASE=http://host.docker.internal:1234/v1
EMBED_MODEL=Qwen3-Embedding-0.6B-GGUF
EMBED_DIM=1024
EMBED_API_KEY=lm-studio

# Recommendation thresholds
RECO_LOW_SCORE=0.60
RECO_MIN_SCORE=0.70
```

### 2) Bring up the stack

```bash
docker compose up -d
```

### 3) Expose callback publicly (quick tunnel)

```bash
cloudflared tunnel --url http://localhost:8003
# copy the printed https://<random>.trycloudflare.com and update PUBLIC_BASE_URL in .env
docker compose up -d --force-recreate core callback
```

### 4) Run DB migrations

```bash
docker compose cp infra/migrations/002_jira_meta.sql postgres:/tmp/002.sql
docker compose exec -T postgres psql -U postgres -d contextual -f /tmp/002.sql

docker compose cp infra/migrations/003_jira_embedding.sql postgres:/tmp/003.sql
docker compose exec -T postgres psql -U postgres -d contextual -f /tmp/003.sql

docker compose cp infra/migrations/005_commit_link.sql postgres:/tmp/005.sql
docker compose exec -T postgres psql -U postgres -d contextual -f /tmp/005.sql
```

### 5) Sync Jira & build embeddings

```bash
# Incremental sync (since last run)
docker compose exec -T core python /app/jobs/jira_sync.py --project ${JIRA_PROJECT_KEY:-SCRUM}

# Embed issues for search
docker compose exec -T core python /app/jobs/embed_jira.py --project ${JIRA_PROJECT_KEY:-SCRUM} --limit 500
```

### 6) Smoke test

```bash
# health checks + DingTalk ping + sample push
bash scripts/smoke.sh
```

### 7) Send a test push (ActionCard expected)

```bash
PAYLOAD='{
  "repository":{"full_name":"demo/contextual"},
  "commits":[{"id":"hello-1234567890","message":"what done + backlog test","added":["a.py"],"modified":["b.md"]}]
}'
SIG='sha256='$(printf "%s" "$PAYLOAD" | openssl dgst -sha256 -hmac "$GIT_WEBHOOK_SECRET" -binary | xxd -p -c 256)
curl -i -X POST http://localhost:8001/ingest/git \
  -H "Content-Type: application/json" -H "X-Hub-Signature-256: $SIG" \
  --data-binary "$PAYLOAD"
```

You should see:

* Core logs: `[RECO] …` then `[DINGTALK RESP] 200 …`
* A DingTalk ActionCard with **Top-1** and candidate buttons
* After clicking, DB rows in `notifications`, `interaction_log`, and **final link** in `commit_links`

---

## Data Model (MVP)

* `jira_projects(project_key, name, raw, updated_at)`
* `jira_issues(jira_key, project_key, title, description, status, priority, assignee, reporter, url, created_at, updated_at, raw, embedding vector(1024))`
* `jira_sync_state(project_key, last_issue_updated, last_run)`
* `notifications(trace_id, tenant_id, commit_hash, recommended_jira_key, confidence, delivered_at, clicked_at)`
* `interaction_log(commit_hash, recommended_jira_key, user_feedback, corrected_jira_key, interaction_timestamp)`
* `commit_links(commit_hash PK, jira_key, project_key, confidence, trace_id, linked_at)`

---

## Ops & Tuning

* **Thresholds**

  * `RECO_MIN_SCORE` — drop low confidence (no card).
  * `RECO_LOW_SCORE` — show a warning title.
* **Rotate PUBLIC_BASE_URL** if quick-tunnel expires; then `docker compose up -d --force-recreate core callback`.
* **Keyword-gated DingTalk bots**: ensure `DINGTALK_KEYWORD` is prefixed in card body (already handled).

---

## Dev Scripts

* `scripts/smoke.sh` — webhook/callback health + DingTalk ping + sample push
* Jobs:

  * `/app/jobs/jira_sync.py`
  * `/app/jobs/embed_jira.py`
  * `/app/jobs/reco_search.py`

---

## Roadmap (next)

* Real-time GitHub/GitLab app integration
* Slack/Teams channels
* Online learning from feedback
* Multi-tenant isolation & RBAC
