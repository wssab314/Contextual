-- 先删旧索引（依赖列类型）
DROP INDEX IF EXISTS idx_jira_issues_embedding_cosine;

-- 将列类型从 384 改为 1024 维
ALTER TABLE jira_issues
  ALTER COLUMN embedding TYPE vector(1024);

-- 重建 ANN 索引（cosine）
CREATE INDEX idx_jira_issues_embedding_cosine
  ON jira_issues
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
