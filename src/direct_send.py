"""Send the daily report directly via Resend, bypassing Klaviyo Flows.

Klaviyo Smart Sending suppresses repeat sends within a 16-hour window,
and the Flow path adds an unpredictable processing delay. For a
deterministic operator-facing daily report we render the template
locally (Jinja2) and POST to Resend.

Activated automatically when RESEND_API_KEY is set.
"""
import os
from pathlib import Path

import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape

from email_payload import build_event_dict

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()

REPORT_FROM_EMAIL = os.environ.get(
    "REPORT_FROM_EMAIL", "reports@passparto.com"
).strip()
REPORT_FROM_NAME = os.environ.get(
    "REPORT_FROM_NAME", "פספרטו · דוח יומי"
).strip()

TEMPLATE_PATH = Path(__file__).resolve().parent.parent
TEMPLATE_FILE = "template.html"


def _render(event_dict):
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_PATH)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=False,
        lstrip_blocks=False,
    )
    return env.get_template(TEMPLATE_FILE).render(event=event_dict)


def send_direct(data, insight):
    """Render the email locally and ship via Resend.

    Returns True on success, False on failure (caller decides whether to
    fall back to the Klaviyo path).
    """
    if not RESEND_API_KEY:
        return False

    to_email = os.environ.get("MICHAEL_EMAIL", "").strip()
    if not to_email:
        print("  [WARN] MICHAEL_EMAIL not set — cannot send direct")
        return False

    event_dict = build_event_dict(data, insight)
    html = _render(event_dict)

    yesterday = data.get("yesterday_date", "")
    subject = f"📊 פספרטו · דוח יומי · {yesterday}" if yesterday else "📊 פספרטו · דוח יומי"

    payload = {
        "from": f"{REPORT_FROM_NAME} <{REPORT_FROM_EMAIL}>",
        "to": [to_email],
        "subject": subject,
        "html": html,
        "tags": [
            {"name": "report", "value": "daily-internal"},
            {"name": "source", "value": "passparto-daily-report"},
        ],
    }

    r = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    if r.status_code in (200, 201, 202):
        msg_id = r.json().get("id", "?")
        print(f"  Direct send (Resend) OK: id={msg_id}  to={to_email}")
        return True
    else:
        print(f"  Resend failed {r.status_code}: {r.text[:300]}")
        return False
