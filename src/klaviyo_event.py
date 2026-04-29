"""Send a 'Daily Internal Report' event to Klaviyo to trigger the Flow.

Passes structured data (arrays of objects) — NOT pre-built HTML.
The Klaviyo template renders the HTML using Jinja2 loops.
"""
import os, requests
from datetime import datetime, timezone

KLAVIYO_KEY = os.environ.get('KLAVIYO_KEY', '')


def send_daily_report_event(data, insight):
    """Send event to Klaviyo with all daily data. Returns True on success."""
    michael_email = os.environ['MICHAEL_EMAIL']

    summary = data['summary']
    ce = data.get('customer_emails', {})

    payload = {
        "data": {
            "type": "event",
            "attributes": {
                "properties": {
                    # Date
                    "yesterday_date": data['yesterday_date'],

                    # Audience
                    "new_subscribers": data['new_subscribers'],
                    "total_profiles": data['total_profiles'],
                    "vip_count": data['segments']['vip'],
                    "repeat_count": data['segments']['repeat'],
                    "at_risk_count": data['segments']['at_risk'],
                    "new_count": data['segments']['new'],
                    "single_buyer_count": data['segments']['single_buyer'],

                    # Campaigns — array of objects with 3 periods each
                    "campaigns": data['campaigns'],

                    # Flows — array of objects with 3 periods each
                    "flows": data['flows'],

                    # Summary — 3 periods
                    "summary": summary,

                    # Convenience fields for simple template access
                    "campaigns_count": len(data['campaigns']),
                    "total_emails_sent": summary['yesterday']['emails_sent'],
                    "total_orders_from_email": summary['yesterday']['orders'],
                    "total_revenue_from_email": summary['yesterday']['revenue'],
                    "aov": summary['yesterday']['aov'],

                    # Customer emails (post-purchase & shipping)
                    "postpurchase_day5_yesterday": ce.get('postpurchase_day5', {}).get('yesterday', 0),
                    "postpurchase_day5_mtd": ce.get('postpurchase_day5', {}).get('month_to_date', 0),
                    "postpurchase_day5_30d": ce.get('postpurchase_day5', {}).get('last_30_days', 0),
                    "postpurchase_day10_yesterday": ce.get('postpurchase_day10', {}).get('yesterday', 0),
                    "postpurchase_day10_mtd": ce.get('postpurchase_day10', {}).get('month_to_date', 0),
                    "postpurchase_day10_30d": ce.get('postpurchase_day10', {}).get('last_30_days', 0),
                    "shipping_yesterday": ce.get('shipping', {}).get('yesterday', 0),
                    "shipping_mtd": ce.get('shipping', {}).get('month_to_date', 0),
                    "shipping_30d": ce.get('shipping', {}).get('last_30_days', 0),

                    # AI insight
                    "insight": insight,
                    "report_time": datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')
                },
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
