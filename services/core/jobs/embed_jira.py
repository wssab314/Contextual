import os, json, time
import requests
import psycopg
from typing import List, Tuple, Optional

PG_HOST = os.environ.get("POSTGRES_HOST","postgres")
PG_DB   = os.environ.get("POSTGRES_DB","contextual")
PG_USER = os.environ.get("POSTGRES_USER","postgres")
PG_PASS = os.environ.get("POSTGRES_PASSWORD","postgres")

EMBED_BASE = os.environ.get("EMBED_API_BASE","http://host.docker.internal:1234/v1").rstrip("/")
EMBED_KEY  = os.environ.get("EMBED_API_KEY","lm-studio")
EMBED_MODEL= os.environ.get("EMBED_MODEL","Qwen3-Embedding-0.6B-GGUF")
EMBED_DIM  = int(os.environ.get("EMBED_DIM","1024"))

def pg_conn():
    dsn = f"host={PG_HOST} dbname={PG_DB} user={PG_USER} password={PG_PASS}"
    return psycopg.connect(dsn)

def _to_text(title: Optional[str], desc: Optional[str]) -> str:
    t = (title or "").strip()
    d = (desc or "").strip()
    # 控制长度，避免极端长文本
    if len(d) > 4000: d = d[:4000]
    return (t + "\n\n" + d).strip()

def _vec_literal(vec: List[float]) -> str:
    # pgvector 的文本字面量，例如: [0.1,0.2,...]
    return "[" + ",".join(str(float(x)) for x in vec) + "]"

def fetch_pending(cur, project_key: str, limit: int) -> List[Tuple[int,str,str,str]]:
    cur.execute("""
        SELECT id, jira_key, title, COALESCE(description,'')
        FROM jira_issues
        WHERE project_key=%s AND embedding IS NULL
        ORDER BY updated_at DESC NULLS LAST, id ASC
        LIMIT %s
    """, (project_key, limit))
    return cur.fetchall()

def embed_batch(texts: List[str]) -> List[List[float]]:
    r = requests.post(
        EMBED_BASE + "/embeddings",
        headers={"Authorization": f"Bearer {EMBED_KEY}"},
        json={"model": EMBED_MODEL, "input": texts},
        timeout=60,
    )
    r.raise_for_status()
    js = r.json()
    vecs = [item["embedding"] for item in js.get("data", [])]
    if not vecs:
        raise RuntimeError(f"Empty embeddings response: {js}")
    # 维度校验
    if len(vecs[0]) != EMBED_DIM:
        raise RuntimeError(f"Embedding dim mismatch: got {len(vecs[0])}, expect {EMBED_DIM}")
    return vecs

def write_embeddings(cur, ids: List[int], vecs: List[List[float]]):
    assert len(ids) == len(vecs)
    for _id, v in zip(ids, vecs):
        cur.execute(
            "UPDATE jira_issues SET embedding = %s::vector WHERE id = %s",
            (_vec_literal(v), _id)
        )

def run(project_key: str, batch_size: int = 32, limit: int = 1000):
    print(f"[EMBED] project={project_key} model={EMBED_MODEL} dim={EMBED_DIM} base={EMBED_BASE}", flush=True)
    total = 0
    with pg_conn() as conn:
        with conn.cursor() as cur:
            while True:
                rows = fetch_pending(cur, project_key, min(batch_size, limit - total))
                if not rows:
                    break
                ids, keys, texts = [], [], []
                for _id, key, title, desc in rows:
                    ids.append(_id); keys.append(key); texts.append(_to_text(title, desc))
                try:
                    vecs = embed_batch(texts)
                except requests.HTTPError as e:
                    # 简单退避重试
                    print(f"[HTTPERR] {e.response.status_code} {e.response.text[:200]}", flush=True)
                    time.sleep(2)
                    vecs = embed_batch(texts)
                write_embeddings(cur, ids, vecs)
                conn.commit()
                total += len(ids)
                print(f"[BATCH] size={len(ids)} total={total} last={keys[-1]}", flush=True)
                if total >= limit:
                    break
    print(f"[DONE] embedded={total}", flush=True)

def _argv():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--limit", type=int, default=1000, help="max rows to process this run")
    return ap.parse_args()

if __name__ == "__main__":
    args = _argv()
    run(args.project, batch_size=args.batch, limit=args.limit)
