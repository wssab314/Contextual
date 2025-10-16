-- Add embedding column (384 dims) if not exists
ALTER TABLE jira_issues
  ADD COLUMN IF NOT EXISTS embedding vector(384);

-- ANN index (cosine). lists 可按规模调整；MVP 先取 100。
CREATE INDEX IF NOT EXISTS idx_jira_issues_embedding_cosine
  ON jira_issues
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
