"""Fetch Cotton Sync status from Airtable Daily Changes table.

Returns inventory-pending count (restock + zero + new_product only)
and last-scan timestamp for the daily email approval line.
Also returns scan_stale flag when last scan > 30 hours ago.
"""
import os
from datetime import datetime, timezone, timedelta

import requests

AIRTABLE_TOKEN = os.environ.get("AIRTABLE_API_TOKEN", "")
BASE_ID = "appJk6ew0rY76D1pD"
TABLE_ID = "tbly6XUUAGgCUIaZ3"
SYSTEM_CONFIG_TABLE = "tbl17eH3vLTUgcfMZ"
HEADERS = {"Authorization": f"Bearer {AIRTABLE_TOKEN}"}

# Only these change types go to Daily Changes / appear in approval count
APPROVAL_TYPES = ("inventory_restock", "inventory_zero", "new_product")


def fetch_cotton_sync_status():
    """Return dict with counts and last scan time.

    - pending_count: total inventory changes pending (restock + zero + new_product)
    - restock_count: inventory_restock pending
    - zero_count: inventory_zero pending
    - last_scan_time: max Date Detected (DD.MM.YYYY HH:MM)
    """
    if not AIRTABLE_TOKEN:
        print("  [WARN] AIRTABLE_API_TOKEN not set — skipping Cotton Sync status")
        return {"pending_count": 0, "restock_count": 0, "zero_count": 0,
                "last_scan_time": "", "scan_stale": False}

    base_url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"
    restock = 0
    zero = 0
    new_prod = 0
    last_scan = ""
    scan_stale = False

    try:
        # Count pending inventory rows by type
        formula = (
            "AND({Status}='Pending',{My Decision}='',"
            "OR({Change Type}='inventory_restock',{Change Type}='inventory_zero',{Change Type}='new_product'))"
        )
        params = {
            "filterByFormula": formula,
            "pageSize": 100,
            "fields[]": ["Change Type"],
        }
        offset = None
        while True:
            if offset:
                params["offset"] = offset
            r = requests.get(base_url, headers=HEADERS, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            for rec in data.get("records", []):
                ct = rec["fields"].get("Change Type", "")
                if ct == "inventory_restock":
                    restock += 1
                elif ct == "inventory_zero":
                    zero += 1
                elif ct == "new_product":
                    new_prod += 1
            offset = data.get("offset")
            if not offset:
                break

        # Last scan time — prefer System Config heartbeat (written every detect run),
        # fall back to Daily Changes Date Detected (only updates when changes exist).
        raw = ""
        try:
            cfg_url = f"https://api.airtable.com/v0/{BASE_ID}/{SYSTEM_CONFIG_TABLE}"
            rc = requests.get(cfg_url, headers=HEADERS, params={
                "filterByFormula": "{Key}='last_detect_run'", "pageSize": 1,
            }, timeout=10)
            rc.raise_for_status()
            cfg_recs = rc.json().get("records", [])
            if cfg_recs:
                raw = cfg_recs[0]["fields"].get("Value", "")
                # New format: "2026-07-09T18:56:08 | step_summary" — extract timestamp
                if " | " in raw:
                    raw = raw.split(" | ")[0].strip()
        except Exception:
            pass
        # Fallback: Daily Changes Date Detected
        if not raw:
            params2 = {
                "sort[0][field]": "Date Detected",
                "sort[0][direction]": "desc",
                "pageSize": 1,
                "fields[]": ["Date Detected"],
            }
            r2 = requests.get(base_url, headers=HEADERS, params=params2, timeout=15)
            r2.raise_for_status()
            recs = r2.json().get("records", [])
            if recs:
                raw = recs[0]["fields"].get("Date Detected", "")

        if raw and "T" in raw:
            date_part, time_part = raw.split("T")
            yy, mm, dd = date_part.split("-")
            hh_mm = time_part[:5]
            last_scan = f"{dd}.{mm} {hh_mm}"
            # Check staleness (>30 hours since last scan)
            try:
                scan_dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                age = datetime.now(timezone.utc) - scan_dt
                scan_stale = age > timedelta(hours=30)
            except Exception:
                pass
        elif raw:
            last_scan = raw

    except Exception as e:
        print(f"  [WARN] Cotton Sync status fetch failed: {e}")

    total = restock + zero + new_prod
    print(f"  Cotton Sync: {total} pending ({restock} restock, {zero} zero, {new_prod} new), scan: {last_scan or '?'}, stale: {scan_stale}")
    return {
        "pending_count": total,
        "restock_count": restock,
        "zero_count": zero,
        "last_scan_time": last_scan,
        "scan_stale": scan_stale,
    }
