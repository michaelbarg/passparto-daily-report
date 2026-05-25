"""Print a live status snapshot for the Passparto daily-report cron.

Reads RENDER_API_KEY (and optional RENDER_SERVICE_ID) from env and queries
Render for:
  - Currently deployed commit and status
  - Configured env vars (key names only — values not exposed)
  - Most recent job run (status, duration, timestamps)
  - Schedule (cron expression and human-readable next-run)

Output is plain text in Hebrew + English, suitable for the chat.

Usage:
  python3 scripts/status.py
"""
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

import requests

API = "https://api.render.com/v1"
DEFAULT_NAME = "passparto-daily-report"


def _need(name):
    v = os.environ.get(name, "").strip()
    if not v:
        sys.exit(f"  Missing env var: {name}")
    return v


def _h(token):
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _resolve_service_id(token):
    sid = os.environ.get("RENDER_SERVICE_ID", "").strip()
    if sid:
        return sid
    r = requests.get(f"{API}/services", params={"limit": 50},
                     headers=_h(token), timeout=20)
    r.raise_for_status()
    for item in r.json():
        svc = item.get("service", item)
        if svc.get("name") == DEFAULT_NAME and svc.get("type") == "cron_job":
            return svc.get("id")
    sys.exit(f"  Could not auto-locate service '{DEFAULT_NAME}'")


def _il_now():
    return datetime.now(timezone(timedelta(hours=3)))


def _next_run(cron_expr):
    """Tiny estimator for '<min> <hour> * * *' style schedules (UTC)."""
    parts = cron_expr.split()
    if len(parts) < 2:
        return "?"
    try:
        minute = int(parts[0])
        hour = int(parts[1])
    except ValueError:
        return "?"
    now_utc = datetime.now(timezone.utc)
    candidate = now_utc.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now_utc:
        candidate = candidate + timedelta(days=1)
    candidate_il = candidate.astimezone(timezone(timedelta(hours=3)))
    return f"{candidate.strftime('%Y-%m-%d %H:%M UTC')} ({candidate_il.strftime('%H:%M')} IL)"


def _humanise_duration(start_iso, end_iso):
    try:
        s = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        sec = int((e - s).total_seconds())
        return f"{sec // 60}m {sec % 60}s"
    except Exception:
        return "?"


def main():
    token = _need("RENDER_API_KEY")
    service_id = _resolve_service_id(token)

    svc_resp = requests.get(f"{API}/services/{service_id}",
                            headers=_h(token), timeout=20)
    svc_resp.raise_for_status()
    svc = svc_resp.json()
    svc_d = svc.get("service", svc) if isinstance(svc.get("service"), dict) else svc

    deploys = requests.get(f"{API}/services/{service_id}/deploys",
                           params={"limit": 1}, headers=_h(token), timeout=20).json()
    deploy = deploys[0].get("deploy", deploys[0]) if deploys else {}

    env_resp = requests.get(f"{API}/services/{service_id}/env-vars",
                            params={"limit": 50}, headers=_h(token), timeout=20).json()
    direct_keys = sorted(item.get("envVar", item).get("key", "") for item in env_resp)

    group_keys = {}
    try:
        groups_list = requests.get(f"{API}/env-groups",
                                   params={"limit": 50},
                                   headers=_h(token), timeout=20).json()
        for item in groups_list:
            g = item.get("envGroup", item)
            gid = g.get("id")
            detail = requests.get(f"{API}/env-groups/{gid}",
                                  headers=_h(token), timeout=20).json()
            linked = [s.get("name") for s in detail.get("serviceLinks", [])]
            if any(svc_d.get("name") == n for n in linked):
                for ev in detail.get("envVars", []):
                    group_keys[ev.get("key", "")] = g.get("name")
    except Exception as e:
        print(f"  [WARN] could not enumerate env groups: {e}")

    env_keys = sorted(set(direct_keys) | set(group_keys.keys()))

    jobs = requests.get(f"{API}/services/{service_id}/jobs",
                        params={"limit": 5}, headers=_h(token), timeout=20).json()

    sd = svc_d.get("serviceDetails") or {}
    cron_expr = sd.get("schedule") or "?"

    print("=" * 60)
    print("  Passparto · Daily Report — Live Status")
    print(f"  Generated {_il_now().strftime('%d.%m.%Y %H:%M')} IL")
    print("=" * 60)

    print(f"\nService:        {svc_d.get('name','?')}  ({service_id})")
    print(f"Type:           {svc_d.get('type','?')}")
    print(f"Schedule:       {cron_expr}  →  next run: {_next_run(cron_expr)}")
    print(f"Repo:           {svc_d.get('repo','?')}")

    print(f"\nDeploy:         {deploy.get('id','?')}  ({deploy.get('status','?')})")
    commit = deploy.get("commit", {})
    print(f"  commit:       {(commit.get('id') or '?')[:8]}  {(commit.get('message') or '').splitlines()[0][:60]}")
    print(f"  finishedAt:   {deploy.get('finishedAt','—')}")

    print(f"\nEnv vars available to service ({len(env_keys)}: "
          f"{len(direct_keys)} direct + {len(group_keys)} via groups):")
    expected = [
        ("KLAVIYO_KEY",                ["KLAVIYO_KEY"],                                  "Klaviyo events + reporting"),
        ("ANTHROPIC_API_KEY",          ["ANTHROPIC_API_KEY"],                            "AI insight generator"),
        ("MICHAEL_EMAIL",              ["MICHAEL_EMAIL"],                                "Recipient profile email"),
        ("KLAVIYO_PLACED_ORDER_METRIC_ID", ["KLAVIYO_PLACED_ORDER_METRIC_ID"],           "Skips a metric-discovery call"),
        ("SHOPIFY_STORE_DOMAIN",       ["SHOPIFY_STORE_DOMAIN", "SHOPIFY_STORE_URL", "SHOPIFY_DOMAIN"], "Shopify domain (live order scan)"),
        ("SHOPIFY_ADMIN_API_TOKEN",    ["SHOPIFY_ADMIN_API_TOKEN", "SHOPIFY_ADMIN_TOKEN", "SHOPIFY_TOKEN"], "Shopify admin token"),
    ]
    matched = set()
    for canonical, aliases, desc in expected:
        found = next((a for a in aliases if a in env_keys), None)
        present = "✓" if found else " "
        suffix = ""
        if found:
            matched.add(found)
            via = group_keys.get(found, "service")
            if found != canonical:
                suffix = f"  (as {found})"
            if via != "service":
                suffix += f"  [via env-group: {via}]"
        print(f"  [{present}] {canonical:32}{suffix}  — {desc}")

    print(f"\nRecent job runs ({len(jobs)}):")
    if not jobs:
        print("  (none yet)")
    for item in jobs:
        j = item.get("job", item)
        dur = _humanise_duration(j.get("startedAt", ""), j.get("finishedAt", ""))
        print(f"  - {j.get('id')}  status={j.get('status'):10}  "
              f"started={j.get('startedAt','—')}  duration={dur}")

    print()


if __name__ == "__main__":
    main()
