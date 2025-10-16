-- Enable pgvector (safe if already exists)
CREATE EXTENSION IF NOT EXISTS vector;

-- Jira Projects
CREATE TABLE IF NOT EXISTS jira_projects (
  id            BIGSERIAL PRIMARY KEY,
  project_key   TEXT UNIQUE NOT NULL,
  name          TEXT NOT NULL,
  raw           JSONB,
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Jira Issues (metadata only for now; embedding column will be added after we choose model/dimension)
CREATE TABLE IF NOT EXISTS jira_issues (
  id              BIGSERIAL PRIMARY KEY,
  jira_key        TEXT UNIQUE NOT NULL,   -- e.g. CTX-123
  project_key     TEXT NOT NULL,          -- e.g. CTX
  title           TEXT NOT NULL,
  description     TEXT,
  status          TEXT,
  priority        TEXT,
  assignee        JSONB,
  reporter        JSONB,
  url             TEXT,
  created_at      TIMESTAMPTZ,
  updated_at      TIMESTAMPTZ,
  raw             JSONB
);

CREATE INDEX IF NOT EXISTS idx_jira_issues_project  ON jira_issues(project_key);
CREATE INDEX IF NOT EXISTS idx_jira_issues_updated  ON jira_issues(updated_at);

-- Sync State (for incremental pulls)
CREATE TABLE IF NOT EXISTS jira_sync_state (
  project_key            TEXT PRIMARY KEY,
  last_issue_updated     TIMESTAMPTZ,
  last_run               TIMESTAMPTZ DEFAULT NOW()
);
