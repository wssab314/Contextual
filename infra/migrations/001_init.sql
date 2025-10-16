CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS user_identity_mapping (
  id SERIAL PRIMARY KEY,
  git_email VARCHAR(255) UNIQUE NOT NULL,
  jira_account_id VARCHAR(255),
  dingtalk_userid VARCHAR(255),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS interaction_log (
  id SERIAL PRIMARY KEY,
  commit_hash VARCHAR(64) NOT NULL,
  recommended_jira_key VARCHAR(50) NOT NULL,
  user_feedback BOOLEAN NOT NULL,
  corrected_jira_key VARCHAR(50),
  interaction_timestamp TIMESTAMPTZ DEFAULT NOW(),
  user_id INT REFERENCES user_identity_mapping(id)
);

CREATE TABLE IF NOT EXISTS commit_events (
  id BIGSERIAL PRIMARY KEY,
  tenant_id VARCHAR(64) NOT NULL,
  repo VARCHAR(255) NOT NULL,
  commit_hash VARCHAR(64) NOT NULL,
  author_email VARCHAR(255),
  message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS notifications (
  id BIGSERIAL PRIMARY KEY,
  trace_id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  commit_hash VARCHAR(64) NOT NULL,
  recommended_jira_key VARCHAR(50),
  confidence NUMERIC,
  dingtalk_msg_id VARCHAR(128),
  delivered_at TIMESTAMPTZ,
  clicked_at TIMESTAMPTZ
);
