#!/usr/bin/env bash
set -euo pipefail

# --- Load env ---------------------------------------------------------------
if [[ -f ".env" ]]; then
  # export everything from .env
  set -a
  source .env
  set +a
else
  echo "[ERR] .env not found"
  exit 1
fi

WEBHOOK_URL="http://localhost:${WEBHOOK_PORT:-8001}"
CALLBACK_HEALTH="${PUBLIC_BASE_URL%/}/health"

echo "== Contextual Smoke Test =="
echo "WEBHOOK_URL = ${WEBHOOK_URL}"
echo "PUBLIC_BASE_URL = ${PUBLIC_BASE_URL:-<unset>}"
echo "DINGTALK_WEBHOOK_URL = ${DINGTALK_WEBHOOK_URL:+<set>}"
echo

# --- 1) Health checks -------------------------------------------------------
echo "[1] Health: webhook (${WEBHOOK_URL}/health)"
curl -sS -m 5 "${WEBHOOK_URL}/health" || { echo "[FAIL] webhook health"; exit 2; }
echo
echo "[1] Health: callback (${CALLBACK_HEALTH})"
curl -sS -m 5 "${CALLBACK_HEALTH}" || { echo "[FAIL] callback health"; exit 3; }
echo

# --- 2) DingTalk connectivity (text) ---------------------------------------
echo "[2] DingTalk text send (keyword required if configured)"
send_ding_text() {
  python3 - <<'PY'
import os, time, hmac, hashlib, base64, urllib.parse, json, sys, requests
url=os.environ.get("DINGTALK_WEBHOOK_URL","")
if not url:
    print("[SKIP] DINGTALK_WEBHOOK_URL not set"); sys.exit(0)
sec=os.environ.get("DINGTALK_SECRET","")
kw = os.environ.get("DINGTALK_KEYWORD","contextual")
def sign(u):
    if not sec: return u
    ts=str(int(time.time()*1000))
    s=f"{ts}\n{sec}".encode()
    sig=urllib.parse.quote_plus(base64.b64encode(hmac.new(sec.encode(), s, hashlib.sha256).digest()).decode())
    return f"{u}&timestamp={ts}&sign={sig}"
u=sign(url)
payload={"msgtype":"text","text":{"content":f"{kw} smoke-check"}}
r=requests.post(u, json=payload, timeout=10)
try: data=r.json()
except: data={"raw": r.text}
print("[HTTP]", r.status_code)
print("[RESP]", json.dumps(data, ensure_ascii=False))
if r.status_code!=200 or (isinstance(data,dict) and data.get("errcode",0)!=0):
    sys.exit(4)
PY
}
send_ding_text || { echo "[FAIL] DingTalk text send"; exit 4; }
echo

# --- 3) Webhook simulate push ----------------------------------------------
echo "[3] Simulate push -> /ingest/git"
PAYLOAD="sample_payload.json"
if [[ ! -f "${PAYLOAD}" ]]; then
cat > "${PAYLOAD}" <<'JSON'
{
  "repository": { "full_name": "smoke/repo" },
  "commits": [{
    "id": "smoketestabcdef1234567890abcdef1234567890",
    "message": "chore: smoke test",
    "author": {"email": "smoke@example.com"},
    "added": ["a.txt"],
    "modified": ["b.py"],
    "removed": []
  }]
}
JSON
fi
SIG="sha256=$(openssl dgst -sha256 -hmac "${GIT_WEBHOOK_SECRET:-replace_me_github_secret}" < "${PAYLOAD}" | sed 's/^.* //')"
curl -sS -i -X POST "${WEBHOOK_URL}/ingest/git" \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: ${SIG}" \
  --data-binary @"${PAYLOAD}" | sed -n '1,5p'
echo
echo "[OK] Smoke test triggered. Check DingTalk for ActionCard."
