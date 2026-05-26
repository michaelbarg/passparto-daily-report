"""Airtable lookups for the daily report.

Two enrichments per Shopify line item, both fetched from the
'cotton-sync' Airtable base (AIRTABLE_BASE_ID env):

  1. Cotton Avenue product name — the operator-friendly name as it
     appears in the Cotton Avenue catalogue, often shorter / cleaner
     than the marketing-tuned Shopify title. Source: 'Open Orders'
     table, keyed by (Order Number, Shopify Product Title).

  2. Supplier — 'Cotton Avenue' or 'Other supplier'. Source: 'Shopify
     Master Catalog', keyed by Shopify Product ID (GID format).

Both lookups are best-effort: if Airtable is missing a row (sync lag,
new product, unmatched item), the email falls back gracefully to the
Shopify name and an empty supplier cell rather than crashing.
"""
import os
import urllib.parse

import requests

AIRTABLE_API_TOKEN = os.environ.get("AIRTABLE_API_TOKEN", "").strip()
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "").strip()

OPEN_ORDERS_TABLE = "Open Orders"
SHOPIFY_MASTER_TABLE = "Shopify Master Catalog"


def _at_get(table, params):
    """Paginated GET against an Airtable table. Returns list of records."""
    if not AIRTABLE_API_TOKEN or not AIRTABLE_BASE_ID:
        return []
    url = (
        f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/"
        f"{urllib.parse.quote(table)}"
    )
    headers = {"Authorization": f"Bearer {AIRTABLE_API_TOKEN}"}
    records = []
    offset = None
    for _ in range(50):
        page_params = list(params)
        page_params.append(("pageSize", "100"))
        if offset:
            page_params.append(("offset", offset))
        try:
            r = requests.get(url, headers=headers, params=page_params, timeout=30)
        except Exception as e:
            print(f"      [WARN] Airtable {table} error: {e}")
            return records
        if r.status_code != 200:
            print(f"      [WARN] Airtable {table} {r.status_code}: {r.text[:200]}")
            return records
        body = r.json()
        records.extend(body.get("records", []))
        offset = body.get("offset")
        if not offset:
            break
    return records


def _chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _escape_formula(s):
    """Escape single quotes for use inside an Airtable filterByFormula string literal."""
    return (s or "").replace("'", "\\'")


def build_open_orders_map(order_numbers):
    """Return a map keyed by (order_number, lower(shopify_title)).

    Each value is a dict with `ca_name` (str, may be empty) and
    `is_excluded` (bool). Order_numbers must include the leading '#'
    just as Airtable stores them.
    """
    if not order_numbers:
        return {}
    out = {}
    for chunk in _chunks(sorted(set(order_numbers)), 30):
        formula = "OR(" + ",".join(
            f"{{Order Number}}='{_escape_formula(n)}'" for n in chunk
        ) + ")"
        recs = _at_get(
            OPEN_ORDERS_TABLE,
            params=[
                ("filterByFormula", formula),
                ("fields[]", "Order Number"),
                ("fields[]", "Shopify Product Title"),
                ("fields[]", "CA Product Name"),
                ("fields[]", "Is Excluded"),
            ],
        )
        for r in recs:
            f = r.get("fields", {})
            on = (f.get("Order Number") or "").strip()
            spt = (f.get("Shopify Product Title") or "").strip().lower()
            if not on or not spt:
                continue
            out[(on, spt)] = {
                "ca_name": (f.get("CA Product Name") or "").strip(),
                "is_excluded": bool(f.get("Is Excluded")),
            }
    return out


def build_supplier_map(product_ids):
    """Return a map of Shopify product_id (numeric str) -> Source Type.

    Source Type is the Cotton Avenue catalogue's tagging:
      - 'Cotton Avenue'    — sourced from Cotton Avenue
      - 'Other supplier'   — anything else
      - ''                 — not in Master Catalog (rare; new product)
    """
    if not product_ids:
        return {}
    pids = sorted({str(p) for p in product_ids if p})
    out = {}
    # FIND(<digits>, {Shopify Product ID}) handles the GID format
    # 'gid://shopify/Product/<digits>' that Airtable stores.
    for chunk in _chunks(pids, 30):
        formula = "OR(" + ",".join(
            f"FIND('{_escape_formula(p)}', {{Shopify Product ID}}&'')>0" for p in chunk
        ) + ")"
        recs = _at_get(
            SHOPIFY_MASTER_TABLE,
            params=[
                ("filterByFormula", formula),
                ("fields[]", "Shopify Product ID"),
                ("fields[]", "Source Type"),
            ],
        )
        for r in recs:
            f = r.get("fields", {})
            sid_raw = str(f.get("Shopify Product ID") or "")
            sid_digits = "".join(c for c in sid_raw if c.isdigit())
            if sid_digits:
                out[sid_digits] = (f.get("Source Type") or "").strip()
    return out


def supplier_label(source_type):
    """Translate a 'Source Type' value into a short Hebrew label for the email."""
    s = (source_type or "").strip().lower()
    if s == "cotton avenue":
        return "Cotton Avenue"
    if s == "other supplier":
        return "אחר"
    return source_type or ""
