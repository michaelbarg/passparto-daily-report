"""Interactive picking sheet web service.

Renders the same unfulfilled-orders list that the daily email shows, but
as a live interactive HTML page with per-row checkboxes, supplier
filters, group-by-order grouping, and a 'Print selected' button that
relies on the browser's native PDF export (no server-side PDF stack).

URL pattern (single endpoint):

  GET /                  HTML page rebuilt from a fresh Shopify query
  GET /healthz           Liveness probe used by Render

This service shares all logic with the cron — orders_collector.py,
supplier_rules.py, etc. — by importing from the repo's `src/` directory.
The free Render Web Service plan hibernates after 15 min idle; the
first request after a sleep takes ~30s to wake.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flask import Flask, render_template

from orders_collector import get_unfulfilled_orders
from supplier_rules import classify_supplier, display_product_name


app = Flask(__name__, template_folder="templates")


def _build_items():
    """Fetch and flatten unfulfilled orders for the picking sheet."""
    orders = get_unfulfilled_orders()
    items = []
    for o in orders:
        for li in o.get("line_items_detail") or []:
            shopify_title = li.get("product", "")
            items.append({
                "product":            display_product_name(shopify_title),
                "supplier":           classify_supplier(shopify_title),
                "size":               li.get("size", ""),
                "color":              li.get("color", ""),
                "quantity":           li.get("quantity", 1),
                "order_number_short": o.get("order_number_short", ""),
                "order_admin_url":    o.get("order_admin_url", ""),
                "is_new_today":       o.get("is_new_today", False),
            })
    return items, len(orders)


@app.get("/")
def picking_sheet():
    items, order_count = _build_items()

    suppliers = sorted({i["supplier"] for i in items if i["supplier"]})
    new_orders_count = sum(
        1 for i in items if i["is_new_today"]
    )  # this counts items, not orders, but useful for feedback

    il_now = datetime.now(timezone(timedelta(hours=3)))

    return render_template(
        "picking_sheet.html",
        items=items,
        order_count=order_count,
        line_item_count=len(items),
        suppliers=suppliers,
        new_count=new_orders_count,
        generated_at=il_now.strftime("%d.%m.%Y %H:%M"),
    )


@app.get("/healthz")
def healthz():
    return {"ok": True}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
