import os, argparse, json
import requests, psycopg

PG_HOST = os.environ.get("POSTGRES_HOST","postgres")
PG_DB   = os.environ.get("POSTGRES_DB","contextual")
PG_USER = os.environ.get("POSTGRES_USER","postgres")
PG_PASS = os.environ.get("POSTGRES_PASSWORD","postgres")

EMBED_BASE  = os.environ.get("EMBED_API_BASE","http://host.docker.internal:1234/v1").rstrip("/")
EMBED_KEY   = os.environ.get("EMBED_API_KEY","lm-studio")
EMBED_MODEL = os.environ.get("EMBED_MODEL","Qwen3-Embedding-0.6B-GGUF")

def _vec_lit(vec):
    return "[" + ",".join(str(float(x)) for x in vec) + "]"

def embed(text: str):
    r = requests.post(
        EMBED_BASE + "/embeddings",
        headers={"Authorization": f"Bearer {EMBED_KEY}"},
        json={"model": EMBED_MODEL, "input": [text]},
        timeout=30
    )
    r.raise_for_status()
    return r.json()["data"][0]["embedding"]

def search(project_key: str, query_vec, topk: int = 5):
    dsn = f"host={PG_HOST} dbname={PG_DB} user={PG_USER} password={PG_PASS}"
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        # 使用 cosine 距离（<=> 越小越近）；同时给出相似度 score = 1 - distance
        vec = _vec_lit(query_vec)
        cur.execute(f"""
            SELECT jira_key, title, status, updated_at,
                   (1 - (embedding <=> %s::vector)) AS score
            FROM jira_issues
            WHERE project_key=%s AND embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector ASC
            LIMIT %s
        """, (vec, project_key, vec, topk))
        rows = cur.fetchall()
    return rows

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--text", required=True, help="query text, e.g. commit msg + filenames")
    ap.add_argument("--topk", type=int, default=3)
    args = ap.parse_args()

    q = args.text.strip()
    print(f"[QUERY] {q}")
    v = embed(q)
    rows = search(args.project, v, args.topk)
    if not rows:
        print("[RESULT] empty")
    else:
        print("[RESULT]")
        for i, (k, title, status, upd, score) in enumerate(rows, 1):
            print(f"{i:2d}. {k:10s}  score={score:.4f}  status={status or '-':6s}  title={title[:80]}")
