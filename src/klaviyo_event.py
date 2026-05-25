"""Send a 'Daily Internal Report' event to Klaviyo to trigger the Flow.

Passes structured data (arrays of objects) — NOT pre-built HTML.
The Klaviyo template renders the HTML using Jinja2 loops.

Used as a fallback path when Resend is not configured. The primary
delivery path is now src/direct_send.py.
"""
import os, requests

from email_payload import build_event_dict

KLAVIYO_KEY = os.environ.get('KLAVIYO_KEY', '')


def send_daily_report_event(data, insight):
    """Send event to Klaviyo with all daily data. Returns True on success."""
    michael_email = os.environ['MICHAEL_EMAIL']
    properties = build_event_dict(data, insight)

    payload = {
        "data": {
            "type": "event",
            "attributes": {
                "properties": properties,
                "metric": {
                    "data": {
                        "type": "metric",
                        "attributes": {"name": "Daily Internal Report"}
                    }
                },
                "profile": {
                    "data": {
                        "type": "profile",
                        "attributes": {"email": michael_email}
                    }
                }
            }
        }
    }

    r = requests.post(
        'https://a.klaviyo.com/api/events/',
        headers={
            'Authorization': f'Klaviyo-API-Key {KLAVIYO_KEY}',
            'revision': '2024-10-15',
            'content-type': 'application/json'
        },
        json=payload,
        timeout=30
    )

    if r.status_code in [200, 201, 202]:
        print(f"  Event sent to Klaviyo for {michael_email}")
        return True
    else:
        print(f"  Event failed: {r.status_code} — {r.text[:200]}")
        return False
