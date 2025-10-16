import os
from fastapi import FastAPI, Request
import psycopg

POSTGRES_DSN = f"host={os.getenv('POSTGRES_HOST','postgres')} dbname={os.getenv('POSTGRES_DB','contextual')} user={os.getenv('POSTGRES_USER','postgres')} password={os.getenv('POSTGRES_PASSWORD','postgres')}"

app = FastAPI()

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/callback/dingtalk")
def cb(trace_id:str, commit:str, jira:str, feedback:bool):
    with psycopg.connect(POSTGRES_DSN) as db:
        db.execute(
          "INSERT INTO interaction_log(commit_hash,recommended_jira_key,user_feedback,interaction_timestamp) VALUES(%s,%s,%s,NOW())",
          (commit, jira, feedback)
        )
        db.execute(
          "UPDATE notifications SET clicked_at=NOW() WHERE trace_id=%s AND commit_hash=%s",
          (trace_id, commit)
        )
    return {"ok": True, "trace_id": trace_id, "commit": commit, "jira": jira, "feedback": feedback}
