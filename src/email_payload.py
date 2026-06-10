"""Build the canonical 'event' dict that the email template consumes.

Used by both klaviyo_event.py (sends as Klaviyo event properties) and
direct_send.py (renders template with it locally and ships via Resend).
"""
import os
from datetime import datetime, timezone

PICKSLIP_URL = os.environ.get(
    "PICKSLIP_URL", "https://passparto-pickslip.onrender.com/"
).strip()


def build_event_dict(data, insight):
    summary = data.get("summary", {})
    yd = summary.get("yesterday", {})
    ce = data.get("customer_emails", {})

    return {
        "yesterday_date": data.get("yesterday_date", ""),

        "new_subscribers": data.get("new_subscribers", 0),
        "total_profiles": data.get("total_profiles", 0),
        "vip_count": data.get("segments", {}).get("vip", 0),
        "repeat_count": data.get("segments", {}).get("repeat", 0),
        "at_risk_count": data.get("segments", {}).get("at_risk", 0),
        "new_count": data.get("segments", {}).get("new", 0),
        "single_buyer_count": data.get("segments", {}).get("single_buyer", 0),

        "campaigns": data.get("campaigns", []),
        "flows": data.get("flows", []),
        "summary": summary,

        "campaigns_count": len(data.get("campaigns", [])),
        "total_emails_sent": yd.get("emails_sent", 0),
        "total_orders_from_email": yd.get("orders", 0),
        "total_revenue_from_email": yd.get("revenue", 0),
        "aov": yd.get("aov", 0),

        "postpurchase_day5_yesterday": ce.get("postpurchase_day5", {}).get("yesterday", 0),
        "postpurchase_day5_mtd": ce.get("postpurchase_day5", {}).get("month_to_date", 0),
        "postpurchase_day5_30d": ce.get("postpurchase_day5", {}).get("last_30_days", 0),
        "postpurchase_day10_yesterday": ce.get("postpurchase_day10", {}).get("yesterday", 0),
        "postpurchase_day10_mtd": ce.get("postpurchase_day10", {}).get("month_to_date", 0),
        "postpurchase_day10_30d": ce.get("postpurchase_day10", {}).get("last_30_days", 0),
        "shipping_yesterday": ce.get("shipping", {}).get("yesterday", 0),
        "shipping_mtd": ce.get("shipping", {}).get("month_to_date", 0),
        "shipping_30d": ce.get("shipping", {}).get("last_30_days", 0),

        "unfulfilled_orders": data.get("unfulfilled_orders", []),
        "unfulfilled_count": data.get("unfulfilled_count", 0),
        "unfulfilled_items": data.get("unfulfilled_items", []),
        "new_orders_count": data.get("new_orders_count", 0),
        # ^ each item dict carries: product, size, color, quantity,
        # supplier ('Cotton Avenue' / 'אחר' / ''), order_number_short,
        # order_admin_url, is_new_today.

        "insight": insight,
        "report_time": datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC"),

        "pickslip_url": PICKSLIP_URL,

        "cs_pending_count": data.get("cs_pending_count", 0),
        "cs_last_scan_time": data.get("cs_last_scan_time", ""),
    }
