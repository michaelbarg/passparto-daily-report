"""Interactive picking sheet / supplier order web service.

Renders unfulfilled-orders as a live interactive HTML page with per-row
checkboxes, supplier filters, editable order-quantity, and a 'Print
selected' button that outputs a supplier order sheet with CA product names.

URL pattern:
  GET /       HTML page rebuilt from a fresh Shopify query
  GET /healthz  Liveness probe
"""
import os
import sys
import requests
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flask import Flask, render_template

from orders_collector import (
    get_unfulfilled_orders,
    SHOPIFY_STORE_DOMAIN,
    SHOPIFY_CLIENT_ID,
    SHOPIFY_CLIENT_SECRET,
    SHOPIFY_ADMIN_API_TOKEN,
    SHOPIFY_API_VERSION,
)
from supplier_rules import classify_supplier, display_product_name


app = Flask(__name__, template_folder="templates")


# ── CA product name lookup via Shopify metafield ────────────────────

def _get_shopify_token():
    """Get a working Shopify access token (OAuth preferred, static fallback)."""
    if SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET:
        try:
            r = requests.post(
                f"https://{SHOPIFY_STORE_DOMAIN}/admin/oauth/access_token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": SHOPIFY_CLIENT_ID,
                    "client_secret": SHOPIFY_CLIENT_SECRET,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
            if r.status_code == 200:
                return r.json().get("access_token", "")
        except Exception:
            pass
    return SHOPIFY_ADMIN_API_TOKEN or ""


def _fetch_ca_names(product_ids):
    """Batch-fetch CA product names from Shopify metafield cotton_sync.ca_product_title.

    Returns dict: product_id (str, numeric) -> ca_name (str).
    """
    if not product_ids or not SHOPIFY_STORE_DOMAIN:
        return {}

    token = _get_shopify_token()
    if not token:
        return {}

    gql_url = f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/{SHOPIFY_API_VERSION}/graphql.json"
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}

    ca_names = {}
    # Process in batches of 50 (GraphQL alias limit)
    unique_ids = list(set(product_ids))
    for batch_start in range(0, len(unique_ids), 50):
        batch = unique_ids[batch_start:batch_start + 50]
        # Build aliased query
        parts = []
        for i, pid in enumerate(batch):
            gid = f"gid://shopify/Product/{pid}"
            parts.append(
                f'p{i}: product(id: "{gid}") {{ '
                f'id metafield(namespace: "cotton_sync", key: "ca_product_title") {{ value }} }}'
            )
        query = "{ " + " ".join(parts) + " }"

        try:
            r = requests.post(gql_url, headers=headers,
                              json={"query": query}, timeout=20)
            if r.status_code != 200:
                continue
            data = r.json().get("data", {})
            for i, pid in enumerate(batch):
                node = data.get(f"p{i}")
                if node and node.get("metafield"):
                    ca_names[pid] = node["metafield"]["value"]
        except Exception as e:
            print(f"  [WARN] CA name batch fetch failed: {e}")
        time.sleep(0.3)

    return ca_names


# ── Airtable fallback for CA names ──────────────────────────────────

AIRTABLE_TOKEN = os.environ.get("AIRTABLE_API_TOKEN", "")
AIRTABLE_BASE = "appJk6ew0rY76D1pD"
AIRTABLE_HEADERS = {"Authorization": f"Bearer {AIRTABLE_TOKEN}"}

_ca_name_cache = {}  # sp_product_title_lower -> ca_name


def _fetch_ca_names_airtable(shopify_titles):
    """Fallback: build SP title → CA name map from Airtable Variant Map.

    Variant Map (tbldO9Wj7CorWbfmY):
      SP Product (flddyeVGPmhryHAgZ) → CA Product (fldlBKjuMzI7YD1i3)
    """
    if not AIRTABLE_TOKEN or not shopify_titles:
        return {}

    if _ca_name_cache:
        return _ca_name_cache

    vm_table = "tbldO9Wj7CorWbfmY"
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE}/{vm_table}"
    params = {
        "pageSize": 100,
        "fields[]": ["CA Product", "SP Product"],
        "filterByFormula": "AND({CA Product}!='',{SP Product}!='')",
    }

    try:
        offset = None
        while True:
            if offset:
                params["offset"] = offset
            r = requests.get(url, headers=AIRTABLE_HEADERS, params=params, timeout=20)
            if r.status_code != 200:
                break
            data = r.json()
            for rec in data.get("records", []):
                f = rec["fields"]
                sp = (f.get("SP Product") or "").strip()
                ca = (f.get("CA Product") or "").strip()
                if sp and ca:
                    _ca_name_cache[sp.lower()] = ca
            offset = data.get("offset")
            if not offset:
                break
            time.sleep(0.25)
    except Exception as e:
        print(f"  [WARN] Airtable CA name fetch failed: {e}")

    print(f"  Airtable CA name cache: {len(_ca_name_cache)} entries")
    return _ca_name_cache


# ── Build items ─────────────────────────────────────────────────────

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
                "product_id":         li.get("product_id", ""),
                "ca_name":            "",  # filled below
            })

    # Batch-fetch CA names from Shopify metafields
    product_ids = [it["product_id"] for it in items if it["product_id"]]
    if product_ids:
        ca_map = _fetch_ca_names(product_ids)
        for it in items:
            it["ca_name"] = ca_map.get(it["product_id"], "")

    # Fallback: fill missing CA names from Airtable Variant Map
    missing = [it for it in items if not it["ca_name"] and it["product"]]
    if missing:
        titles = [it["product"] for it in missing]
        at_map = _fetch_ca_names_airtable(titles)
        for it in missing:
            ca = at_map.get(it["product"].lower())
            if ca:
                it["ca_name"] = ca

    filled = sum(1 for it in items if it["ca_name"])
    print(f"  CA names: {filled}/{len(items)} filled")

    return items, len(orders)


@app.get("/")
def picking_sheet():
    items, order_count = _build_items()

    suppliers = sorted({i["supplier"] for i in items if i["supplier"]})
    new_orders_count = sum(
        1 for i in items if i["is_new_today"]
    )

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
