"""Fetch Cotton Sync status from Airtable Daily Changes table.

Returns pending-change count and last-scan timestamp for the daily email.
"""
import os

import requests

AIRTABLE_TOKEN = os.environ.get("AIRTABLE_API_TOKEN", "")
BASE_ID = "appJk6ew0rY76D1pD"
TABLE_ID = "tbly6XUUAGgCUIaZ3"
HEADERS = {"Authorization": f"Bearer {AIRTABLE_TOKEN}"}


def fetch_cotton_sync_status():
    """Return dict with pending_count and last_scan_time.

    - pending_count: rows where Status='Pending' AND My Decision is empty
    - last_scan_time: max Date Detected across all rows (DD.MM.YYYY HH:MM)
    """
    if not AIRTABLE_TOKEN:
        print("  [WARN] AIRTABLE_API_TOKEN not set — skipping Cotton Sync status")
        return {"pending_count": 0, "last_scan_time": ""}

    base_url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"
    pending_count = 0
    last_scan = ""

    try:
        # 1) Count pending rows (Status=Pending, My Decision empty)
        params = {
            "filterByFormula": "AND({Status}='Pending',{My Decision}='')",
            "pageSize": 100,
            "fields[]": ["Status"],
        }
        offset = None
        while True:
            if offset:
                params["offset"] = offset
            r = requests.get(base_url, headers=HEADERS, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            pending_count += len(data.get("records", []))
            offset = data.get("offset")
            if not offset:
                break

        # 2) Last scan time — most recent Date Detected
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
            # Airtable ISO format: 2026-06-08T08:00:00.000Z → 08.06.2026 08:00
            if raw and "T" in raw:
                date_part, time_part = raw.split("T")
                yy, mm, dd = date_part.split("-")
                hh_mm = time_part[:5]
                last_scan = f"{dd}.{mm}.{yy} {hh_mm}"
            elif raw:
                last_scan = raw

    except Exception as e:
        print(f"  [WARN] Cotton Sync status fetch failed: {e}")

    print(f"  Cotton Sync: {pending_count} pending, last scan: {last_scan or '?'}")
    return {"pending_count": pending_count, "last_scan_time": last_scan}
