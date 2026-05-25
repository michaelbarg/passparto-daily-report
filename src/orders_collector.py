"""Collect unfulfilled orders.

Two sources, in priority order:

  1. **Shopify Admin API** (preferred — live source of truth)
     Used when SHOPIFY_STORE_DOMAIN and SHOPIFY_ADMIN_API_TOKEN are set.
     Hits /admin/api/.../orders.json?fulfillment_status=unfulfilled,partial
     so the daily email always reflects the *current* state of the store
     at the moment the report runs.

  2. **Klaviyo events** (fallback)
     Diffs Placed Order vs Fulfilled Order events from the last 14 days.

Output row shape (one per unfulfilled order):
{
    "order_number":    "#1234",
    "order_id":        "5567743202xxx",
    "placed_at":       "23.05.2026",
    "days_open":       2,
    "customer_name":   "ישראל ישראלי",
    "address":         "רחוב הרצל 10, דירה 4, תל אביב 6473820",
    "phone":           "+972501234567",
    "items_summary":   "2x מצעים פרימיום, 1x מגבת חוף",
    "total":           "350.00",
}
"""
import os
import time
import requests
from datetime import datetime, timedelta, timezone

KLAVIYO_KEY = os.environ.get("KLAVIYO_KEY", "")
KLAVIYO_HEADERS = {
    "Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
    "revision": "2024-10-15",
    "accept": "application/json",
    "content-type": "application/json",
}

def _normalize_shopify_domain(raw):
    """Accept any of: bare subdomain, full *.myshopify.com, or full https URL."""
    s = (raw or "").strip()
    if not s:
        return ""
    s = s.replace("https://", "").replace("http://", "")
    s = s.rstrip("/")
    if "/" in s:
        s = s.split("/", 1)[0]
    if "." not in s:
        s = f"{s}.myshopify.com"
    return s


SHOPIFY_STORE_DOMAIN = _normalize_shopify_domain(
    os.environ.get("SHOPIFY_STORE_DOMAIN")
    or os.environ.get("SHOPIFY_STORE_URL")
    or os.environ.get("SHOPIFY_DOMAIN")
    or ""
)

SHOPIFY_ADMIN_API_TOKEN = (
    os.environ.get("SHOPIFY_ADMIN_API_TOKEN")
    or os.environ.get("SHOPIFY_ADMIN_TOKEN")
    or os.environ.get("SHOPIFY_TOKEN")
    or ""
).strip()

SHOPIFY_API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2024-10").strip()

LOOKBACK_DAYS = int(os.environ.get("UNFULFILLED_LOOKBACK_DAYS", "14"))
MAX_ORDERS_IN_EMAIL = int(os.environ.get("UNFULFILLED_MAX_IN_EMAIL", "50"))

PLACED_ORDER_METRIC_ID = os.environ.get("KLAVIYO_PLACED_ORDER_METRIC_ID", "")
FULFILLED_ORDER_METRIC_ID = os.environ.get("KLAVIYO_FULFILLED_ORDER_METRIC_ID", "")


# ─── Metric discovery ────────────────────────────────────────

def _discover_metric_id(metric_name):
    """Find the metric ID for a given metric name (e.g. 'Placed Order')."""
    url = "https://a.klaviyo.com/api/metrics/"
    params = {"page[size]": 100}
    while url:
        r = requests.get(url, params=params, headers=KLAVIYO_HEADERS, timeout=30)
        if r.status_code != 200:
            print(f"      [WARN] metrics list {r.status_code}: {r.text[:120]}")
            return ""
        body = r.json()
        for m in body.get("data", []):
            if m.get("attributes", {}).get("name") == metric_name:
                return m["id"]
        url = body.get("links", {}).get("next")
        params = None
    return ""


def _ensure_metric_ids():
    """Make sure Placed/Fulfilled metric IDs are known. Returns (placed, fulfilled)."""
    global PLACED_ORDER_METRIC_ID, FULFILLED_ORDER_METRIC_ID
    if not PLACED_ORDER_METRIC_ID:
        PLACED_ORDER_METRIC_ID = _discover_metric_id("Placed Order")
    if not FULFILLED_ORDER_METRIC_ID:
        FULFILLED_ORDER_METRIC_ID = _discover_metric_id("Fulfilled Order")
    return PLACED_ORDER_METRIC_ID, FULFILLED_ORDER_METRIC_ID


# ─── Event fetching ──────────────────────────────────────────

def _fmt_utc(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch_events(metric_id, since_utc, max_pages=20):
    """Return raw event objects with profile included (since `since_utc`)."""
    if not metric_id:
        return []

    url = "https://a.klaviyo.com/api/events/"
    params = {
        "filter": (
            f"and(equals(metric_id,\"{metric_id}\"),"
            f"greater-than(datetime,{_fmt_utc(since_utc)}))"
        ),
        "include": "profile",
        "page[size]": 100,
        "sort": "-datetime",
    }

    events = []
    profiles_by_id = {}
    pages = 0

    while url and pages < max_pages:
        for attempt in range(3):
            try:
                r = requests.get(url, params=params, headers=KLAVIYO_HEADERS, timeout=30)
                if r.status_code == 429:
                    wait = 10 * (attempt + 1)
                    print(f"      [429] events list — waiting {wait}s...")
                    time.sleep(wait)
                    continue
                if r.status_code != 200:
                    print(f"      [WARN] events {r.status_code}: {r.text[:200]}")
                    return events, profiles_by_id
                break
            except Exception as e:
                print(f"      [WARN] events fetch error: {e}")
                if attempt == 2:
                    return events, profiles_by_id
                time.sleep(5)

        body = r.json()
        events.extend(body.get("data", []))
        for inc in body.get("included", []):
            if inc.get("type") == "profile":
                profiles_by_id[inc["id"]] = inc.get("attributes", {})

        url = body.get("links", {}).get("next")
        params = None
        pages += 1
        time.sleep(0.3)

    return events, profiles_by_id


# ─── Event helpers ───────────────────────────────────────────

def _event_order_id(event):
    """Extract a stable order identifier from an event."""
    props = event.get("attributes", {}).get("event_properties", {}) or {}
    for key in ("OrderId", "order_id", "$event_id"):
        v = props.get(key)
        if v:
            return str(v)
    extra = event.get("attributes", {}).get("extra", {}) or {}
    for key in ("OrderId", "order_id"):
        v = extra.get(key)
        if v:
            return str(v)
    return None


def _format_address(addr):
    """Build a one-line Hebrew-readable address from a Shopify-style address dict."""
    if not isinstance(addr, dict):
        return ""
    parts = []
    line1 = " ".join(filter(None, [addr.get("Address1"), addr.get("Address2")])).strip()
    if line1:
        parts.append(line1)
    city_zip = " ".join(
        filter(None, [addr.get("City"), str(addr.get("Zip") or "").strip()])
    ).strip()
    if city_zip:
        parts.append(city_zip)
    country = addr.get("Country") or addr.get("CountryPrefixCode")
    if country and country not in ("IL", "Israel", "ישראל"):
        parts.append(str(country))
    return ", ".join(parts)


def _customer_name(event, profile_attrs):
    """Best-effort customer full name."""
    props = event.get("attributes", {}).get("event_properties", {}) or {}
    for key in ("Billing Address", "Shipping Address"):
        a = props.get(key)
        if isinstance(a, dict):
            full = " ".join(
                filter(None, [a.get("FirstName"), a.get("LastName")])
            ).strip()
            if full:
                return full

    if profile_attrs:
        full = " ".join(
            filter(
                None,
                [profile_attrs.get("first_name"), profile_attrs.get("last_name")],
            )
        ).strip()
        if full:
            return full
        if profile_attrs.get("email"):
            return profile_attrs["email"]
    return "—"


def _items_summary(event, max_items=3):
    """Compact 'qty x title' summary of order items."""
    props = event.get("attributes", {}).get("event_properties", {}) or {}
    items = props.get("Items") or props.get("items") or []
    if not isinstance(items, list):
        return ""
    parts = []
    for it in items[:max_items]:
        if not isinstance(it, dict):
            continue
        qty = it.get("Quantity") or it.get("quantity") or 1
        title = (
            it.get("Product Name")
            or it.get("ProductName")
            or it.get("Title")
            or it.get("title")
            or ""
        )
        if title:
            parts.append(f"{qty}× {title}")
    if len(items) > max_items:
        parts.append(f"+{len(items) - max_items}")
    return ", ".join(parts)


def _days_open(placed_iso, now):
    """Whole days between placed_iso and now."""
    try:
        placed = datetime.fromisoformat(placed_iso.replace("Z", "+00:00"))
    except Exception:
        return 0
    return max(0, (now - placed).days)


# ─── Shopify Admin API source (preferred) ───────────────────

def _shopify_format_address(addr):
    """Build a one-line address string from Shopify shipping_address dict."""
    if not isinstance(addr, dict):
        return ""
    parts = []
    line1 = " ".join(filter(None, [addr.get("address1"), addr.get("address2")])).strip()
    if line1:
        parts.append(line1)
    city_zip = " ".join(
        filter(None, [addr.get("city"), str(addr.get("zip") or "").strip()])
    ).strip()
    if city_zip:
        parts.append(city_zip)
    country = addr.get("country") or addr.get("country_code")
    if country and country not in ("IL", "Israel", "ישראל"):
        parts.append(str(country))
    return ", ".join(parts)


def _shopify_items_summary(line_items, max_items=3):
    """Compact 'qty x title' summary from Shopify line_items list."""
    if not isinstance(line_items, list):
        return ""
    parts = []
    for it in line_items[:max_items]:
        title = it.get("title") or it.get("name") or ""
        qty = it.get("quantity") or 1
        if title:
            parts.append(f"{qty}× {title}")
    if len(line_items) > max_items:
        parts.append(f"+{len(line_items) - max_items}")
    return ", ".join(parts)


def _from_shopify():
    """Pull live unfulfilled orders straight from the Shopify Admin API."""
    base = f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/{SHOPIFY_API_VERSION}/orders.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_ADMIN_API_TOKEN,
        "accept": "application/json",
    }
    params = {
        "status": "any",
        "fulfillment_status": "unfulfilled,partial",
        "financial_status": "paid,partially_paid,authorized,partially_refunded",
        "limit": 250,
        "fields": (
            "id,name,created_at,total_price,currency,fulfillment_status,"
            "financial_status,cancelled_at,closed_at,customer,shipping_address,"
            "billing_address,line_items,phone,note"
        ),
    }

    print(f"    Shopify: GET {SHOPIFY_STORE_DOMAIN}/admin/.../orders.json"
          f" (fulfillment_status=unfulfilled,partial)")

    orders = []
    url = base
    pages = 0
    while url and pages < 10:
        for attempt in range(3):
            r = requests.get(url, params=params if pages == 0 else None,
                             headers=headers, timeout=30)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "5"))
                print(f"      [429] Shopify — waiting {wait}s...")
                time.sleep(wait)
                continue
            break
        if r.status_code != 200:
            raise RuntimeError(f"Shopify {r.status_code}: {r.text[:200]}")

        page_orders = r.json().get("orders", [])
        orders.extend(page_orders)
        pages += 1

        link = r.headers.get("Link", "")
        next_url = ""
        for chunk in link.split(","):
            if 'rel="next"' in chunk:
                next_url = chunk.split(";")[0].strip().lstrip("<").rstrip(">")
                break
        url = next_url
        time.sleep(0.3)

    print(f"      {len(orders)} unfulfilled orders returned by Shopify")

    now = datetime.now(timezone.utc)
    rows = []
    for o in orders:
        if o.get("cancelled_at") or o.get("closed_at"):
            continue

        ship = o.get("shipping_address") or o.get("billing_address") or {}

        first = (ship.get("first_name") if isinstance(ship, dict) else "") or ""
        last = (ship.get("last_name") if isinstance(ship, dict) else "") or ""
        customer_name = (f"{first} {last}").strip()
        if not customer_name:
            cust = o.get("customer") or {}
            customer_name = (
                f"{cust.get('first_name','') or ''} {cust.get('last_name','') or ''}"
            ).strip() or cust.get("email", "—") or "—"

        phone = ""
        if isinstance(ship, dict):
            phone = ship.get("phone") or ""
        if not phone:
            phone = o.get("phone") or (o.get("customer") or {}).get("phone") or ""

        created_iso = o.get("created_at") or ""
        try:
            created_dt = datetime.fromisoformat(created_iso.replace("Z", "+00:00"))
            placed_str = created_dt.astimezone(
                timezone(timedelta(hours=3))
            ).strftime("%d.%m.%Y")
            days_open = max(0, (now - created_dt).days)
        except Exception:
            placed_str = ""
            days_open = 0

        try:
            total_str = f"{float(o.get('total_price') or 0):.2f}"
        except Exception:
            total_str = str(o.get("total_price") or "0")

        rows.append({
            "order_number":  o.get("name") or f"#{o.get('id','')}",
            "order_id":      str(o.get("id", "")),
            "placed_at":     placed_str,
            "days_open":     days_open,
            "customer_name": customer_name,
            "address":       _shopify_format_address(ship),
            "phone":         phone,
            "items_summary": _shopify_items_summary(o.get("line_items") or []),
            "total":         total_str,
        })

        if len(rows) >= MAX_ORDERS_IN_EMAIL:
            break

    rows.sort(key=lambda r: r["days_open"], reverse=True)
    return rows


# ─── Main entry point ────────────────────────────────────────

def get_unfulfilled_orders():
    """Return a list of unfulfilled orders, newest first.

    Prefers Shopify Admin API (live state). Falls back to Klaviyo events
    if Shopify isn't configured or the call fails.

    Token env vars accepted (first non-empty wins):
        SHOPIFY_ADMIN_API_TOKEN, SHOPIFY_ADMIN_TOKEN, SHOPIFY_TOKEN
    Domain env vars accepted:
        SHOPIFY_STORE_DOMAIN, SHOPIFY_DOMAIN
        (defaults to passparto.myshopify.com if neither is set)
    """
    if SHOPIFY_ADMIN_API_TOKEN and SHOPIFY_STORE_DOMAIN:
        try:
            print(f"    Source: Shopify Admin API (live data from {SHOPIFY_STORE_DOMAIN})")
            rows = _from_shopify()
            print(f"    => {len(rows)} unfulfilled orders (Shopify)")
            return rows
        except Exception as e:
            print(f"    [WARN] Shopify lookup failed ({e}) — falling back to Klaviyo")
    else:
        missing = []
        if not SHOPIFY_ADMIN_API_TOKEN:
            missing.append("SHOPIFY_ADMIN_API_TOKEN/SHOPIFY_ADMIN_TOKEN")
        if not SHOPIFY_STORE_DOMAIN:
            missing.append("SHOPIFY_STORE_DOMAIN")
        print(f"    Shopify not configured (missing: {', '.join(missing)}) — using Klaviyo fallback")

    print("    Source: Klaviyo events (Placed Order minus Fulfilled Order)")
    return _from_klaviyo()


def _from_klaviyo():
    """Diff Klaviyo Placed Order vs Fulfilled Order events."""
    placed_id, fulfilled_id = _ensure_metric_ids()
    if not placed_id:
        print("  [WARN] 'Placed Order' metric not found — skipping unfulfilled orders")
        return []

    now = datetime.now(timezone.utc)
    placed_since = now - timedelta(days=LOOKBACK_DAYS)
    fulfilled_since = now - timedelta(days=LOOKBACK_DAYS + 7)

    print(f"    Fetching Placed Order events since {_fmt_utc(placed_since)}...")
    placed_events, placed_profiles = _fetch_events(placed_id, placed_since)
    print(f"      {len(placed_events)} placed events")

    fulfilled_ids = set()
    if fulfilled_id:
        print(f"    Fetching Fulfilled Order events since {_fmt_utc(fulfilled_since)}...")
        fulfilled_events, _ = _fetch_events(fulfilled_id, fulfilled_since)
        print(f"      {len(fulfilled_events)} fulfilled events")
        for e in fulfilled_events:
            oid = _event_order_id(e)
            if oid:
                fulfilled_ids.add(oid)
    else:
        print("    [WARN] 'Fulfilled Order' metric not found — every order will appear unfulfilled")

    seen_orders = set()
    rows = []
    for ev in placed_events:
        oid = _event_order_id(ev)
        if not oid or oid in seen_orders or oid in fulfilled_ids:
            continue
        seen_orders.add(oid)

        attrs = ev.get("attributes", {})
        props = attrs.get("event_properties", {}) or {}
        placed_iso = attrs.get("datetime") or attrs.get("timestamp") or ""

        profile_id = (
            ev.get("relationships", {})
            .get("profile", {})
            .get("data", {})
            .get("id")
        )
        profile_attrs = placed_profiles.get(profile_id, {})

        ship = props.get("Shipping Address") or props.get("Billing Address") or {}

        order_number = (
            props.get("$event_id")
            or props.get("OrderNumber")
            or props.get("order_number")
            or oid
        )
        order_number_str = str(order_number)
        if not order_number_str.startswith("#"):
            order_number_str = f"#{order_number_str}"

        try:
            placed_dt = datetime.fromisoformat(placed_iso.replace("Z", "+00:00"))
            placed_il = placed_dt.astimezone(timezone(timedelta(hours=3)))
            placed_str = placed_il.strftime("%d.%m.%Y")
        except Exception:
            placed_str = ""

        total_raw = props.get("$value") or props.get("Total") or 0
        try:
            total_str = f"{float(total_raw):.2f}"
        except Exception:
            total_str = str(total_raw)

        phone = ""
        if isinstance(ship, dict):
            phone = ship.get("Phone") or ship.get("phone") or ""
        if not phone and profile_attrs:
            phone = profile_attrs.get("phone_number", "") or ""

        rows.append({
            "order_number":  order_number_str,
            "order_id":      oid,
            "placed_at":     placed_str,
            "days_open":     _days_open(placed_iso, now),
            "customer_name": _customer_name(ev, profile_attrs),
            "address":       _format_address(ship),
            "phone":         phone,
            "items_summary": _items_summary(ev),
            "total":         total_str,
        })

        if len(rows) >= MAX_ORDERS_IN_EMAIL:
            break

    rows.sort(key=lambda r: r["days_open"], reverse=True)
    print(f"    => {len(rows)} unfulfilled orders (Klaviyo)")
    return rows
