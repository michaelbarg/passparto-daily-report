"""Trigger a one-off run of the Passparto daily-report cron on Render.

Render does NOT expose SSH for cron services — this is the supported
remote-trigger path. Two env vars are required:

  RENDER_API_KEY      Personal API token (https://dashboard.render.com/u/settings#api-keys)
  RENDER_SERVICE_ID   The cron's id, e.g. crn-XXXXXXXXXXXX
                      (Found in the URL when the cron is open in the dashboard:
                       https://dashboard.render.com/cron/<RENDER_SERVICE_ID>)

Optional:
  RENDER_JOB_COMMAND  Override the start command for this run only.
                      Defaults to the service's configured startCommand.

Usage:
  python3 scripts/trigger_now.py
"""
import json
import os
import sys
import time

import requests

API = "https://api.render.com/v1"


def _need(name):
    v = os.environ.get(name, "").strip()
    if not v:
        sys.exit(
            f"\n  Missing env var: {name}\n"
            f"  Add it to Cursor Dashboard ▸ Cloud Agents ▸ Secrets, "
            f"then re-run.\n"
        )
    return v


def _headers(token):
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _service_info(token, service_id):
    r = requests.get(f"{API}/services/{service_id}", headers=_headers(token), timeout=20)
    if r.status_code != 200:
        sys.exit(f"  Service lookup failed ({r.status_code}): {r.text[:200]}")
    return r.json()


def _trigger_job(token, service_id, override_cmd):
    """Create a one-off job. Render's API: POST /v1/services/{id}/jobs"""
    body = {}
    if override_cmd:
        body["startCommand"] = override_cmd

    r = requests.post(
        f"{API}/services/{service_id}/jobs",
        headers=_headers(token),
        json=body,
        timeout=30,
    )
    if r.status_code in (200, 201):
        return r.json()

    if r.status_code == 404:
        print("  /jobs endpoint not available for this service — "
              "falling back to manual deploy trigger.")
        r2 = requests.post(
            f"{API}/services/{service_id}/deploys",
            headers=_headers(token),
            json={"clearCache": "do_not_clear"},
            timeout=30,
        )
        if r2.status_code in (200, 201):
            return {"_via": "deploy", **r2.json()}
        sys.exit(f"  Deploy trigger failed ({r2.status_code}): {r2.text[:200]}")

    sys.exit(f"  Job trigger failed ({r.status_code}): {r.text[:300]}")


def _poll_job(token, service_id, job_id, max_wait=180):
    """Poll a job until it finishes or we hit the timeout."""
    start = time.time()
    last_status = ""
    while time.time() - start < max_wait:
        r = requests.get(
            f"{API}/services/{service_id}/jobs/{job_id}",
            headers=_headers(token),
            timeout=20,
        )
        if r.status_code != 200:
            print(f"      [poll {r.status_code}] {r.text[:120]}")
            return None
        info = r.json()
        status = info.get("status", "?")
        if status != last_status:
            print(f"    job {job_id}: {status}")
            last_status = status
        if status in ("succeeded", "failed", "canceled"):
            return info
        time.sleep(4)
    print(f"    (timed out after {max_wait}s — check Render dashboard for outcome)")
    return None


def main():
    token = _need("RENDER_API_KEY")
    service_id = _need("RENDER_SERVICE_ID")
    override_cmd = os.environ.get("RENDER_JOB_COMMAND", "").strip() or None

    print(f"Render trigger: service {service_id}")

    info = _service_info(token, service_id)
    svc = info.get("service", info)
    print(f"  Service: {svc.get('name','?')}  type={svc.get('type','?')}")

    job = _trigger_job(token, service_id, override_cmd)
    job_id = job.get("id") or job.get("deploy", {}).get("id")
    via = job.get("_via", "job")
    print(f"  Triggered ({via}): id={job_id}")

    if via == "job" and job_id:
        result = _poll_job(token, service_id, job_id)
        if result:
            print(f"\nFinal status: {result.get('status')}")
            print(json.dumps({
                "createdAt": result.get("createdAt"),
                "startedAt": result.get("startedAt"),
                "finishedAt": result.get("finishedAt"),
                "status": result.get("status"),
            }, indent=2))


if __name__ == "__main__":
    main()
