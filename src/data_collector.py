"""Collect yesterday's data from Klaviyo + segmentation results.

Returns structured data with 3 time periods per campaign/flow:
  - yesterday: just yesterday (24h)
  - month_to_date: 1st of month through yesterday
  - last_30_days: rolling 30-day window
"""
import os, json, time, requests
from datetime import datetime, timedelta, timezone

from orders_collector import get_unfulfilled_orders

KLAVIYO_KEY = os.environ.get("KLAVIYO_KEY", "")
KLAVIYO_HEADERS = {
    'Authorization': f'Klaviyo-API-Key {KLAVIYO_KEY}',
    'revision': '2024-10-15',
    'accept': 'application/json',
    'content-type': 'application/json'
}

PLACED_ORDER_METRIC_ID = os.environ.get('KLAVIYO_PLACED_ORDER_METRIC_ID', '')

SEGMENTATION_RESULTS = os.environ.get(
    'SEGMENTATION_RESULTS_PATH',
    os.path.expanduser('~/passparto-segmentation/discovery_results.json')
)

STATS_FIELDS = ["recipients", "opens_unique", "clicks_unique",
                "conversion_uniques", "conversion_value"]

# Post-purchase & shipping flow message IDs
CUSTOMER_EMAIL_MESSAGES = {
    'postpurchase_day5':  {'flow_id': 'Ryput8', 'message_id': 'QVnrQv'},
    'postpurchase_day10': {'flow_id': 'Ryput8', 'message_id': 'WiE6mW'},
    'shipping':           {'flow_id': 'SDb4ZA', 'message_id': 'We2Q2y'},
}


# ─── Time windows ────────────────────────────────────────────

def _get_time_windows():
    """Return 3 time windows as (label, start_utc, end_utc) tuples."""
    il_tz = timezone(timedelta(hours=3))
    now_il = datetime.now(il_tz)
    yesterday = now_il - timedelta(days=1)

    yd_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
    yd_end = yesterday.replace(hour=23, minute=59, second=59, microsecond=0)

    mtd_start = yesterday.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    d30_start = (yesterday - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)

    return [
        ('yesterday',     yd_start.astimezone(timezone.utc),  yd_end.astimezone(timezone.utc)),
        ('month_to_date', mtd_start.astimezone(timezone.utc), yd_end.astimezone(timezone.utc)),
        ('last_30_days',  d30_start.astimezone(timezone.utc), yd_end.astimezone(timezone.utc)),
    ]


def _fmt_utc(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


# ─── Profiles / segments ─────────────────────────────────────

def count_new_subscribers(start_utc, end_utc):
    """Count profiles created yesterday."""
    count = 0
    url = 'https://a.klaviyo.com/api/profiles/'
    params = {
        'filter': f'and(greater-than(created,{_fmt_utc(start_utc)}),less-than(created,{_fmt_utc(end_utc)}))',
        'page[size]': 100
    }
    while url:
        r = requests.get(url, params=params, headers=KLAVIYO_HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        count += len(data.get('data', []))
        url = data.get('links', {}).get('next')
        params = None
    return count


def get_segmentation_data():
    """Read latest segment counts from discovery_results.json."""
    if not os.path.exists(SEGMENTATION_RESULTS):
        print(f"  [WARN] {SEGMENTATION_RESULTS} not found — using zeros")
        return {
            'total_profiles': 0,
            'segments': {'vip': 0, 'repeat': 0, 'at_risk': 0, 'new': 0, 'single_buyer': 0},
        }
    with open(SEGMENTATION_RESULTS, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    seg = raw.get('segment_counts', {})
    return {
        'total_profiles': raw.get('total_profiles', 0),
        'segments': {
            'vip': seg.get('segment_vip', 0),
            'repeat': seg.get('segment_repeat', 0),
            'at_risk': seg.get('segment_at_risk', 0),
            'new': seg.get('segment_new', 0),
            'single_buyer': seg.get('segment_single_buyer', seg.get('segment_disengaged', 0)),
        },
    }


# ─── Klaviyo reporting helpers ────────────────────────────────

def _api_report(endpoint, type_name, filter_str, timeframe):
    """Single Klaviyo report call with retry on 429."""
    body = {
        "data": {
            "type": type_name,
            "attributes": {
                "statistics": STATS_FIELDS,
                "timeframe": timeframe,
                "filter": filter_str,
                "conversion_metric_id": PLACED_ORDER_METRIC_ID
            }
        }
    }
    for attempt in range(3):
        try:
            r = requests.post(
                f'https://a.klaviyo.com/api/{endpoint}/',
                headers=KLAVIYO_HEADERS, json=body, timeout=30
            )
            if r.status_code == 200:
                return r.json().get('data', {}).get('attributes', {}).get('results', [])
            elif r.status_code == 429:
                wait = 10 * (attempt + 1)
                print(f"      [429] waiting {wait}s...")
                time.sleep(wait)
                continue
            else:
                print(f"      [WARN] {endpoint} {r.status_code}: {r.text[:120]}")
                return []
        except Exception as e:
            print(f"      [WARN] {endpoint} error: {e}")
            return []
    return []


def _parse_stats(raw_stats):
    """Convert raw API stats to a clean dict."""
    sent = int(raw_stats.get('recipients', 0))
    opens = int(raw_stats.get('opens_unique', 0))
    clicks = int(raw_stats.get('clicks_unique', 0))
    orders = int(raw_stats.get('conversion_uniques', 0))
    revenue = round(raw_stats.get('conversion_value', 0), 2)
    return {
        'sent': sent,
        'opens': opens,
        'open_rate': round((opens / sent * 100), 1) if sent > 0 else 0,
        'clicks': clicks,
        'click_rate': round((clicks / sent * 100), 1) if sent > 0 else 0,
        'orders': orders,
        'revenue': revenue,
    }


def _sum_result_rows(rows):
    """Sum statistics across multiple result rows (e.g. flow messages)."""
    totals = {k: 0 for k in STATS_FIELDS}
    for row in rows:
        stats = row.get('statistics', {})
        for k in totals:
            totals[k] += stats.get(k, 0)
    return totals


# ─── Campaign metrics (3 periods) ────────────────────────────

def get_campaign_metrics(time_windows):
    """For each campaign sent yesterday, return metrics across 3 periods."""
    yd_start, yd_end = time_windows[0][1], time_windows[0][2]

    r = requests.get(
        'https://a.klaviyo.com/api/campaigns/',
        params={
            'filter': f'and(equals(messages.channel,"email"),greater-or-equal(send_time,{_fmt_utc(yd_start)}),less-than(send_time,{_fmt_utc(yd_end)}))',
            'page[size]': 50
        },
        headers=KLAVIYO_HEADERS, timeout=30
    )
    campaigns = r.json().get('data', []) if r.status_code == 200 else []

    results = []
    for campaign in campaigns:
        cid = campaign['id']
        name = campaign.get('attributes', {}).get('name', 'Unknown')
        print(f"    Campaign: {name} ...")

        periods = {}
        for label, w_start, w_end in time_windows:
            tf = {'start': _fmt_utc(w_start), 'end': _fmt_utc(w_end)}
            rows = _api_report('campaign-values-reports', 'campaign-values-report',
                               f'equals(campaign_id,"{cid}")', tf)
            raw = rows[0].get('statistics', {}) if rows else {}
            periods[label] = _parse_stats(raw)
            time.sleep(1)

        results.append({'name': name, **periods})

    return results


# ─── Flow metrics (3 periods) ────────────────────────────────

def get_flow_metrics(time_windows):
    """For each active Flow, return metrics across 3 periods."""
    r = requests.get(
        'https://a.klaviyo.com/api/flows/',
        params={'filter': 'equals(status,"live")', 'page[size]': 50},
        headers=KLAVIYO_HEADERS, timeout=30
    )
    flows = r.json().get('data', []) if r.status_code == 200 else []

    results = []
    for flow in flows:
        fid = flow['id']
        name = flow.get('attributes', {}).get('name', 'Unknown')
        print(f"    Flow: {name} ...")

        periods = {}
        has_activity = False
        for label, w_start, w_end in time_windows:
            tf = {'start': _fmt_utc(w_start), 'end': _fmt_utc(w_end)}
            rows = _api_report('flow-values-reports', 'flow-values-report',
                               f'equals(flow_id,"{fid}")', tf)
            raw = _sum_result_rows(rows)
            parsed = _parse_stats(raw)
            periods[label] = parsed
            if parsed['sent'] > 0:
                has_activity = True
            time.sleep(1)

        if has_activity:
            results.append({'name': name, **periods})

    return results


# ─── Summary ─────────────────────────────────────────────────

def _build_summary(campaigns, flows):
    """Build summary across 3 periods."""
    summary = {}
    for period in ('yesterday', 'month_to_date', 'last_30_days'):
        emails = sum(c[period]['sent'] for c in campaigns) + sum(f[period]['sent'] for f in flows)
        orders = sum(c[period]['orders'] for c in campaigns) + sum(f[period]['orders'] for f in flows)
        revenue = sum(c[period]['revenue'] for c in campaigns) + sum(f[period]['revenue'] for f in flows)
        aov = round(revenue / orders, 2) if orders > 0 else 0
        summary[period] = {
            'emails_sent': emails,
            'orders': orders,
            'revenue': round(revenue, 2),
            'aov': aov,
        }
    return summary


# ─── Customer email metrics (per flow message) ──────────────

def get_customer_email_metrics(time_windows):
    """Get send counts for specific flow messages across 3 periods."""
    results = {}

    for label, info in CUSTOMER_EMAIL_MESSAGES.items():
        flow_id = info['flow_id']
        message_id = info['message_id']
        print(f"    {label} (flow={flow_id}, msg={message_id}) ...")

        periods = {}
        for period_name, w_start, w_end in time_windows:
            tf = {'start': _fmt_utc(w_start), 'end': _fmt_utc(w_end)}
            rows = _api_report(
                'flow-values-reports', 'flow-values-report',
                f'equals(flow_id,"{flow_id}")', tf
            )
            # Find the specific message in the results
            count = 0
            for row in rows:
                if row.get('groupings', {}).get('flow_message_id') == message_id:
                    count = int(row.get('statistics', {}).get('recipients', 0))
                    break
            periods[period_name] = count
            time.sleep(1)

        results[label] = periods

    return results


# ─── Main collector ──────────────────────────────────────────

def collect_all():
    """Collect all daily data into a single dict."""
    time_windows = _get_time_windows()
    yd_start, yd_end = time_windows[0][1], time_windows[0][2]
    yesterday_str = (datetime.now(timezone(timedelta(hours=3))) - timedelta(days=1)).strftime('%d.%m.%Y')

    seg_data = get_segmentation_data()

    print("  Fetching new subscribers...")
    new_subs = count_new_subscribers(yd_start, yd_end)

    print("  Fetching campaign metrics (3 periods)...")
    campaigns = get_campaign_metrics(time_windows)

    print("  Fetching flow metrics (3 periods)...")
    flows = get_flow_metrics(time_windows)

    print("  Fetching customer email metrics...")
    customer_emails = get_customer_email_metrics(time_windows)

    print("  Fetching unfulfilled orders...")
    unfulfilled_orders = get_unfulfilled_orders()

    unfulfilled_items = []
    for o in unfulfilled_orders:
        for li in o.get("line_items_detail") or []:
            unfulfilled_items.append({
                "product": li["product"],
                "size": li["size"],
                "quantity": li["quantity"],
                "order_number_short": o.get("order_number_short", ""),
                "order_admin_url": o.get("order_admin_url", ""),
                "is_new_today": o.get("is_new_today", False),
            })

    new_orders_count = sum(1 for o in unfulfilled_orders if o.get("is_new_today"))

    summary = _build_summary(campaigns, flows)

    data = {
        'yesterday_date': yesterday_str,
        'new_subscribers': new_subs,
        'total_profiles': seg_data['total_profiles'],
        'segments': seg_data['segments'],
        'campaigns': campaigns,
        'flows': flows,
        'customer_emails': customer_emails,
        'unfulfilled_orders': unfulfilled_orders,
        'unfulfilled_count': len(unfulfilled_orders),
        'unfulfilled_items': unfulfilled_items,
        'new_orders_count': new_orders_count,
        'summary': summary,
    }

    s = summary['yesterday']
    print(f"  Yesterday: {s['emails_sent']} emails, {s['orders']} orders, ₪{s['revenue']}")
    s30 = summary['last_30_days']
    print(f"  30 days:   {s30['emails_sent']} emails, {s30['orders']} orders, ₪{s30['revenue']}")
    print(f"  Unfulfilled orders open: {len(unfulfilled_orders)}")
    return data
