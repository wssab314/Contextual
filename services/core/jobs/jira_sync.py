import os, sys, time, json, datetime as dt
from typing import Dict, Any, Optional
import requests
import psycopg

JIRA_URL = os.environ.get("JIRA_URL","").rstrip("/")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL","")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN","")

PG_HOST = os.environ.get("POSTGRES_HOST","postgres")
PG_DB   = os.environ.get("POSTGRES_DB","contextual")
PG_USER = os.environ.get("POSTGRES_USER","postgres")
PG_PASS = os.environ.get("POSTGRES_PASSWORD","postgres")

def pg_conn():
    dsn = f"host={PG_HOST} dbname={PG_DB} user={PG_USER} password={PG_PASS}"
    return psycopg.connect(dsn)

def _plain_text_description(desc):
    if not desc:
        return None
    if isinstance(desc, str):
        return desc
    try:
        def walk(node):
            t = node.get("type")
            if t == "text":
                return node.get("text","")
            if "content" in node and isinstance(node["content"], list):
                return "".join(walk(c) for c in node["content"])
            return ""
        return walk(desc)
    except Exception:
        return None

def _upsert_project(cur, project_key: str, name: str, raw: Dict[str,Any]):
    cur.execute("""
        INSERT INTO jira_projects(project_key, name, raw, updated_at)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (project_key) DO UPDATE
        SET name=EXCLUDED.name, raw=EXCLUDED.raw, updated_at=NOW()
    """, (project_key, name, json.dumps(raw)))

def _upsert_issue(cur, issue: Dict[str,Any]):
    key = issue["key"]
    f = issue.get("fields", {}) or {}
    proj_key = (f.get("project") or {}).get("key") or key.split("-")[0]
    title = f.get("summary") or ""
    desc_plain = _plain_text_description(f.get("description"))
    status = (f.get("status") or {}).get("name")
    priority = (f.get("priority") or {}).get("name")
    assignee = f.get("assignee")
    reporter = f.get("reporter")
    url = f"{JIRA_URL}/browse/{key}"

    def parse_ts(s):
        if not s: return None
        try:
            return dt.datetime.fromisoformat(s.replace("Z","+00:00"))
        except Exception:
            return None
    created_ts = parse_ts(f.get("created"))
    updated_ts = parse_ts(f.get("updated"))

    cur.execute("""
        INSERT INTO jira_issues(
            jira_key, project_key, title, description, status, priority,
            assignee, reporter, url, created_at, updated_at, raw
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (jira_key) DO UPDATE SET
            project_key=EXCLUDED.project_key,
            title=EXCLUDED.title,
            description=EXCLUDED.description,
            status=EXCLUDED.status,
            priority=EXCLUDED.priority,
            assignee=EXCLUDED.assignee,
            reporter=EXCLUDED.reporter,
            url=EXCLUDED.url,
            created_at=COALESCE(EXCLUDED.created_at, jira_issues.created_at),
            updated_at=COALESCE(EXCLUDED.updated_at, jira_issues.updated_at),
            raw=EXCLUDED.raw
    """, (
        key, proj_key, title, desc_plain, status, priority,
        json.dumps(assignee) if assignee else None,
        json.dumps(reporter) if reporter else None,
        url, created_ts, updated_ts, json.dumps(issue)
    ))

def _get_sync_state(cur, project_key: str):
    cur.execute("SELECT last_issue_updated FROM jira_sync_state WHERE project_key=%s", (project_key,))
    row = cur.fetchone()
    return row[0] if row else None

def _set_sync_state(cur, project_key: str, last_updated: Optional[dt.datetime]):
    cur.execute("""
        INSERT INTO jira_sync_state(project_key, last_issue_updated, last_run)
        VALUES (%s, %s, NOW())
        ON CONFLICT (project_key) DO UPDATE
          SET last_issue_updated = EXCLUDED.last_issue_updated,
              last_run = NOW()
    """, (project_key, last_updated))

def _jira_search_page(project_key: str, since: Optional[dt.datetime], next_token: Optional[str]):
    jql = f'project = "{project_key}"'
    if since:
        jql += f" AND updated >= '{since.strftime('%Y-%m-%d %H:%M')}'"
    jql += " ORDER BY updated ASC"

    body = {
        "jql": jql,
        "maxResults": 100,
        "fields": ["summary","description","status","priority","assignee","reporter","project","created","updated"]
    }
    if next_token:
        body["nextPageToken"] = next_token

    r = requests.post(f"{JIRA_URL}/rest/api/3/search/jql",
                      json=body, auth=(JIRA_EMAIL, JIRA_API_TOKEN), timeout=30)
    if r.status_code == 429:
        time.sleep(2)
        return _jira_search_page(project_key, since, next_token)
    r.raise_for_status()
    js = r.json()
    issues = js.get("issues", []) or (js.get("data", {}) or {}).get("issues", [])
    return issues, js.get("nextPageToken"), js.get("isLast", js.get("nextPageToken") is None)

def sync_project(project_key: str, full: bool=False, since_cli: Optional[str]=None):
    assert JIRA_URL and JIRA_EMAIL and JIRA_API_TOKEN, "Missing Jira config"

    proj = requests.get(f"{JIRA_URL}/rest/api/3/project/{project_key}",
                        auth=(JIRA_EMAIL, JIRA_API_TOKEN), timeout=30)
    proj.raise_for_status()
    proj_js = proj.json()
    proj_name = proj_js.get("name") or project_key

    with pg_conn() as conn:
        with conn.cursor() as cur:
            _upsert_project(cur, project_key, proj_name, proj_js)
            since = None if full else _get_sync_state(cur, project_key)
            if since_cli:
                try: since = dt.datetime.fromisoformat(since_cli)
                except Exception: pass

            print(f"[SYNC] project={project_key} name={proj_name} since={since} full={full}", flush=True)

            total = 0
            max_updated = since
            token = None
            while True:
                issues, token, is_last = _jira_search_page(project_key, since, token)
                for it in issues:
                    _upsert_issue(cur, it)
                    upd = (it.get("fields") or {}).get("updated")
                    if upd:
                        try:
                            ts = dt.datetime.fromisoformat(upd.replace("Z","+00:00"))
                            if (max_updated is None) or (ts > max_updated):
                                max_updated = ts
                        except Exception:
                            pass
                conn.commit()
                batch = len(issues)
                total += batch
                print(f"[BATCH] token={'<start>' if token is None else str(token)[:8]} size={batch} total={total}", flush=True)
                if is_last or batch == 0:
                    break

            _set_sync_state(cur, project_key, max_updated)
            conn.commit()
            print(f"[DONE] total={total} last_updated={max_updated}", flush=True)

def _argv():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, help="Jira project key, e.g. SCRUM")
    ap.add_argument("--full", action="store_true", help="Full sync (ignore stored state)")
    ap.add_argument("--since", help="Override since ISO timestamp, e.g. 2025-01-01T00:00:00+00:00")
    return ap.parse_args()

if __name__ == "__main__":
    args = _argv()
    try:
        sync_project(args.project, full=args.full, since_cli=args.since)
    except Exception as e:
        print("ERR", type(e).__name__, str(e))
        sys.exit(2)
