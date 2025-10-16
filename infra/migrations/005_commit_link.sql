-- 最终 commit→Jira 关联表（每个 commit 保持 1 行，后写覆盖）
CREATE TABLE IF NOT EXISTS commit_links (
    commit_hash  text PRIMARY KEY,
    jira_key     text NOT NULL,
    project_key  text,
    confidence   double precision,
    trace_id     text,
    linked_at    timestamptz NOT NULL DEFAULT NOW()
);

-- 常用查询索引
CREATE INDEX IF NOT EXISTS idx_commit_links_jira ON commit_links(jira_key);
CREATE INDEX IF NOT EXISTS idx_commit_links_project ON commit_links(project_key);
