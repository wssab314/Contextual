import hmac, hashlib, os, json
import pika
from fastapi import FastAPI, Header, Request, HTTPException

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")
GIT_SECRET = os.getenv("GIT_WEBHOOK_SECRET", "replace_me_github_secret")

QUEUE_RAW = "git_commit_raw"

app = FastAPI()

def _channel():
    creds = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    conn = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST, credentials=creds))
    ch = conn.channel()
    ch.queue_declare(queue=QUEUE_RAW, durable=True)
    return conn, ch

@app.get("/health")
def health():
    return {"ok": True}

def verify_github_sig(sig256: str, body: bytes):
    if not sig256 or not sig256.startswith("sha256="):
        return False
    digest = hmac.new(GIT_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, sig256.split("=",1)[1])

@app.post("/ingest/git")
async def ingest(request: Request, x_hub_signature_256: str = Header(None)):
    body = await request.body()
    if not verify_github_sig(x_hub_signature_256, body):
        raise HTTPException(status_code=401, detail="invalid signature")

    payload = json.loads(body)
    # 提取最小字段（为空则给默认）
    repo = payload.get("repository",{}).get("full_name","unknown/repo")
    tenant_id = "tenant-demo"
    for commit in payload.get("commits",[]):
        msg = {
            "schema_version":"1.0",
            "trace_id": commit.get("id",""),
            "tenant_id": tenant_id,
            "event_type":"git_commit_raw",
            "payload":{
                "repo": repo,
                "commit_hash": commit.get("id","")[:12],
                "author_email": commit.get("author",{}).get("email",""),
                "message": commit.get("message",""),
                "files_changed": len(commit.get("modified",[])+commit.get("added",[])+commit.get("removed",[]))
            }
        }
        conn, ch = _channel()
        ch.basic_publish(exchange="", routing_key=QUEUE_RAW, body=json.dumps(msg).encode(), properties=pika.BasicProperties(delivery_mode=2))
        conn.close()
    return {"accepted": True}
