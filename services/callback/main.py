import os
from typing import Optional
from fastapi import FastAPI
import psycopg

POSTGRES_DSN = f"host={os.getenv('POSTGRES_HOST','postgres')} dbname={os.getenv('POSTGRES_DB','contextual')} user={os.getenv('POSTGRES_USER','postgres')} password={os.getenv('POSTGRES_PASSWORD','postgres')}"

app = FastAPI()

@app.get("/health")
def health():
    return {"ok": True}

def _project_from(jira_key: str) -> Optional[str]:
    if not jira_key:
        return None
    return jira_key.split("-", 1)[0] if "-" in jira_key else None

@app.get("/callback/dingtalk")
def cb(
    trace_id: str,
    commit: str,
    jira: str,              # 兼容旧版参数
    feedback: bool,
    top1: Optional[str] = None,
    selected: Optional[str] = None,
):
    recommended = (top1 or jira).strip()
    clicked = (selected or jira).strip()

    corrected = None
    if feedback and clicked and (clicked != recommended):
        corrected = clicked

    with psycopg.connect(POSTGRES_DSN) as db, db.cursor() as cur:
        # 1) 交互日志
        cur.execute(
            "INSERT INTO interaction_log(commit_hash,recommended_jira_key,user_feedback,corrected_jira_key,interaction_timestamp) VALUES(%s,%s,%s,%s,NOW())",
            (commit, recommended, feedback, corrected)
        )
        # 2) 标记通知被点击
        cur.execute(
            "UPDATE notifications SET clicked_at=NOW() WHERE trace_id=%s AND commit_hash=%s",
            (trace_id, commit)
        )

        # 3) 若确认（feedback=true），把“最终选择”UPSERT到 commit_links
        if feedback:
            final_jira = clicked  # 用户最后点的就是最终选择
            project_key = _project_from(final_jira)

            # 取置信度（没有就 NULL）
            cur.execute(
                "SELECT confidence FROM notifications WHERE trace_id=%s AND commit_hash=%s ORDER BY delivered_at DESC LIMIT 1",
                (trace_id, commit)
            )
            row = cur.fetchone()
            confidence = float(row[0]) if row and row[0] is not None else None

            cur.execute(
                """
                INSERT INTO commit_links (commit_hash, jira_key, project_key, confidence, trace_id, linked_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (commit_hash) DO UPDATE
                SET jira_key = EXCLUDED.jira_key,
                    project_key = EXCLUDED.project_key,
                    confidence = EXCLUDED.confidence,
                    trace_id = EXCLUDED.trace_id,
                    linked_at = NOW()
                """,
                (commit, final_jira, project_key, confidence, trace_id)
            )

    return {
        "ok": True,
        "trace_id": trace_id,
        "commit": commit,
        "jira": jira,
        "feedback": feedback,
        "top1": recommended,
        "selected": clicked,
        "corrected": corrected,
        "linked": clicked if feedback else None,
    }
