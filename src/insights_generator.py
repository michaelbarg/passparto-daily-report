"""Generate a single daily insight using Anthropic API."""
import os, requests


def generate_insight(data):
    """Return a short Hebrew insight (50-80 words)."""
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return "אין מפתח Anthropic — תובנה לא זמינה"

    campaigns_summary = ""
    for c in data.get('campaigns', []):
        yd = c.get('yesterday', {})
        d30 = c.get('last_30_days', {})
        campaigns_summary += (
            f"- {c['name']}: אתמול נשלח {yd.get('sent',0)}, "
            f"פתיחה {yd.get('open_rate',0)}%, רכישות {yd.get('orders',0)}, ₪{yd.get('revenue',0)} | "
            f"30 יום: נשלח {d30.get('sent',0)}, רכישות {d30.get('orders',0)}, ₪{d30.get('revenue',0)}\n"
        )

    flows_summary = ""
    for f in data.get('flows', []):
        yd = f.get('yesterday', {})
        d30 = f.get('last_30_days', {})
        flows_summary += (
            f"- {f['name']}: אתמול נשלח {yd.get('sent',0)}, "
            f"פתיחה {yd.get('open_rate',0)}%, רכישות {yd.get('orders',0)}, ₪{yd.get('revenue',0)} | "
            f"30 יום: נשלח {d30.get('sent',0)}, רכישות {d30.get('orders',0)}, ₪{d30.get('revenue',0)}\n"
        )

    s = data.get('summary', {})
    yd_s = s.get('yesterday', {})
    d30_s = s.get('last_30_days', {})

    prompt = f"""אתה יועץ שיווק בעברית של חנות מצעים ומגבות ישראלית בשם פספרטו.
נתוני אתמול:

בסיס:
- נרשמים חדשים: {data['new_subscribers']}
- סה"כ פרופילים: {data['total_profiles']}
- VIPs: {data['segments']['vip']} | At Risk: {data['segments']['at_risk']}

פעילות מיילים:
{f"קמפיינים:{chr(10)}{campaigns_summary}" if campaigns_summary else "לא יצאו קמפיינים אתמול"}
{f"Flows:{chr(10)}{flows_summary}" if flows_summary else "אין פעילות Flows אתמול"}

סיכום אתמול: {yd_s.get('emails_sent',0)} מיילים, {yd_s.get('orders',0)} רכישות, ₪{yd_s.get('revenue',0)}, AOV ₪{yd_s.get('aov',0)}
סיכום 30 יום: {d30_s.get('emails_sent',0)} מיילים, {d30_s.get('orders',0)} רכישות, ₪{d30_s.get('revenue',0)}, AOV ₪{d30_s.get('aov',0)}

תן תובנה אחת קצרה (50-80 מילים) בעברית, מקצועית, מועילה.
זהה את הדבר הכי חשוב לתשומת לב — אם יש Flow ללא רכישות, קמפיין עם פתיחה גבוהה אבל קליק נמוך, או הזדמנות שלא נוצלה. לא רק לחזור על המספרים."""

    r = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        },
        json={
            'model': 'claude-haiku-4-5-20251001',
            'max_tokens': 300,
            'messages': [{'role': 'user', 'content': prompt}]
        },
        timeout=30
    )

    if r.status_code == 200:
        return r.json()['content'][0]['text'].strip()
    return f"תובנה לא זמינה (API error: {r.status_code})"
