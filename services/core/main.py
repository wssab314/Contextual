import os, json, time, base64, hmac, hashlib, urllib.parse
import pika, requests
import psycopg
from fastapi import FastAPI

# ===== env & consts =====
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST","rabbitmq")
RABBITMQ_USER = os.getenv("RABBITMQ_USER","guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD","guest")
QUEUE_RAW = "git_commit_raw"

POSTGRES_DSN = f"host={os.getenv('POSTGRES_HOST','postgres')} dbname={os.getenv('POSTGRES_DB','contextual')} user={os.getenv('POSTGRES_USER','postgres')} password={os.getenv('POSTGRES_PASSWORD','postgres')}"
DING_URL = os.getenv("DINGTALK_WEBHOOK_URL","")
DING_SECRET = os.getenv("DINGTALK_SECRET","")
PUBLIC_BASE = os.getenv("PUBLIC_BASE_URL","http://localhost:8003")

# embedding / jira
EMBED_BASE  = os.getenv("EMBED_API_BASE","http://host.docker.internal:1234/v1").rstrip("/")
EMBED_KEY   = os.getenv("EMBED_API_KEY","lm-studio")
EMBED_MODEL = os.getenv("EMBED_MODEL","Qwen3-Embedding-0.6B-GGUF")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY","SCRUM")

# 阈值：低置信度提示 & 抑制发送
CONFIDENCE_WARN = float(os.getenv("RECO_LOW_SCORE", "0.60"))  # 低于此在标题上提示
RECO_MIN_SCORE  = float(os.getenv("RECO_MIN_SCORE", "0.70"))  # 低于此不发卡片（直接丢弃）

app = FastAPI()

@app.get("/health")
def health():
    return {"ok": True}

# ===== DingTalk helpers =====
def ding_sign_url(base_url:str, secret:str):
    ts = str(int(time.time() * 1000))
    string_to_sign = f"{ts}\n{secret}".encode("utf-8")
    h = hmac.new(secret.encode("utf-8"), string_to_sign, digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(h))
    return f"{base_url}&timestamp={ts}&sign={sign}"

def send_action_card(trace_id:str, commit_hash:str, repo:str, top1_key:str, candidates=None, score:float=None):
    url = ding_sign_url(DING_URL, DING_SECRET) if DING_SECRET and "sign=" not in DING_URL else DING_URL
    keyword = os.getenv("DINGTALK_KEYWORD","").strip()

    # 文案
    title = "是否关联到该 Jira 任务？"
    if score is not None and score < CONFIDENCE_WARN:
        title = "（低置信度）是否关联到该 Jira 任务？"

    body_lines = [
        "**Contextual 推荐关联**",
        f"仓库：{repo}",
        f"Commit：`{commit_hash}`",
        "",
        f"猜测的 Jira：**{top1_key}**" + (f"（置信度 {score:.2f}）" if score is not None else "")
    ]

    # === 带上 top1 / selected 参数 ===
    def cb_url(jira_key:str, fb:bool, selected:str=None):
        sel = selected or jira_key
        base = f"{PUBLIC_BASE}/callback/dingtalk"
        q = {
            "trace_id": trace_id,
            "commit": commit_hash,
            "jira": jira_key,          # 兼容旧版
            "feedback": "true" if fb else "false",
            "top1": top1_key,
            "selected": sel
        }
        return base + "?" + urllib.parse.urlencode(q)

    btns = []
    btns.append({"title":"✅ Yes, link it", "actionURL": cb_url(top1_key, True, selected=top1_key)})

    if candidates:
        body_lines.append("")
        body_lines.append("**其它候选：**")
        for k, s in candidates:
            if k == top1_key:
                continue
            body_lines.append(f"- {k}（{s:.2f}）")
            btns.append({"title": f"👉 {k}", "actionURL": cb_url(k, True, selected=k)})

    btns.append({"title":"❌ Not sure", "actionURL": cb_url(top1_key, False, selected=top1_key)})

    body_text = "\n".join(body_lines)
    if keyword:
        body_text = f"{keyword}\n\n" + body_text

    payload = {
        "msgtype": "actionCard",
        "actionCard": {
            "title": title,
            "text": body_text,
            "btns": btns[:4],   # 钉钉建议 ≤4 个按钮
            "btnOrientation":"0"
        }
    }
    r = requests.post(url, json=payload, timeout=(5, 10))
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    print("[DINGTALK RESP]", r.status_code, data)
    r.raise_for_status()
    if isinstance(data, dict) and data.get("errcode",0)!=0:
        raise RuntimeError(f"DingTalk send failed: {data}")
    return data

# ===== Embedding & Search helpers =====
def _vec_lit(vec):
    return "[" + ",".join(str(float(x)) for x in vec) + "]"

def embed_text(text:str):
    r = requests.post(
        EMBED_BASE + "/embeddings",
        headers={"Authorization": f"Bearer {EMBED_KEY}"},
        json={"model": EMBED_MODEL, "input": [text]},
        timeout=(5, 30)
    )
    r.raise_for_status()
    js = r.json()
    return js["data"][0]["embedding"]

def search_topk(project_key:str, query_vec, k:int=3):
    vec = _vec_lit(query_vec)
    with psycopg.connect(POSTGRES_DSN) as db, db.cursor() as cur:
        cur.execute(f"""
            SELECT jira_key, (1 - (embedding <=> %s::vector)) AS score
            FROM jira_issues
            WHERE project_key=%s AND embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector ASC
            LIMIT %s
        """, (vec, project_key, vec, k))
        rows = cur.fetchall()
    return rows  # [(key, score), ...]

def build_query_from_payload(p:dict) -> str:
    msg = p.get("commit_message") or p.get("message")
    if not msg:
        msg = (p.get("head_commit") or {}).get("message")
    if not msg and isinstance(p.get("commits"), list):
        msgs = [c.get("message","") for c in p["commits"] if c.get("message")]
        msg = "; ".join(msgs)[:500] if msgs else None

    files = []
    hc = p.get("head_commit") or {}
    for k in ("added","modified","removed"):
        li = hc.get(k) or []
        if isinstance(li, list):
            files.extend(li)
    files = files[:10]

    repo = p.get("repo") or (p.get("repository") or {}).get("full_name") or ""
    parts = []
    if msg: parts.append(msg)
    if files: parts.append("files: " + ", ".join(files))
    if repo: parts.append(f"repo:{repo}")
    if not parts:
        parts = ["code change"]
    return "\n".join(parts)

# ===== MQ consumer =====
def consume():
    creds = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    conn = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST, credentials=creds))
    ch = conn.channel()
    ch.queue_declare(queue=QUEUE_RAW, durable=True)

    def _cb(chx, method, props, body):
        msg = json.loads(body)
        p = msg.get("payload",{})
        repo = p.get("repo","") or (p.get("repository") or {}).get("full_name","")
        commit_hash = p.get("commit_hash","") or (p.get("head_commit") or {}).get("id","")[:12]
        trace_id = msg.get("trace_id","")

        # === embedding 检索 Top-K ===
        top1 = "DEMO-1"; score = None; candidates = None
        try:
            query_text = build_query_from_payload(p)
            qvec = embed_text(query_text)
            rows = search_topk(JIRA_PROJECT_KEY, qvec, k=3)
            if rows:
                candidates = rows
                top1, score = rows[0]
                print(f"[RECO] project={JIRA_PROJECT_KEY} top1={top1} score={score:.4f} q='{query_text[:120]}'")
            else:
                print("[RECO] no candidate, fallback DEMO-1")
        except Exception as e:
            print("reco error:", e, "fallback DEMO-1")

        # === 低分抑制：低于 RECO_MIN_SCORE 则不发卡片 ===
        try:
            if isinstance(score, (int,float)) and score < RECO_MIN_SCORE:
                print(f"[RECO DROP] top1={top1} score={score:.4f} < {RECO_MIN_SCORE:.2f}, skip sending")
                chx.basic_ack(delivery_tag=method.delivery_tag)
                return

            res = send_action_card(trace_id, commit_hash, repo, top1, candidates=candidates, score=score)
            confidence = float(score) if isinstance(score, (int,float)) else 0.5
            with psycopg.connect(POSTGRES_DSN) as db:
                db.execute(
                    "INSERT INTO notifications(trace_id,tenant_id,commit_hash,recommended_jira_key,confidence,delivered_at) VALUES(%s,%s,%s,%s,%s,NOW())",
                    (trace_id,"tenant-demo", commit_hash, top1, confidence)
                )
            chx.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            print("send ding error:", e)
            chx.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    ch.basic_qos(prefetch_count=10)
    ch.basic_consume(queue=QUEUE_RAW, on_message_callback=_cb)
    print(" [*] Core consuming. Ctrl+C to exit.")
    try:
        ch.start_consuming()
    except KeyboardInterrupt:
        ch.stop_consuming()
    conn.close()

# 启动消费线程
import threading
t = threading.Thread(target=consume, daemon=True)
t.start()
