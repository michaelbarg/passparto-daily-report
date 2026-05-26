# Passparto Daily Report — Status

> 🔒 **נעול ופעיל**. מייל יומי אוטומטי דרך Resend, נתונים חיים מ-Shopify.
>
> מסמך זה הוא **המקור האחד** למצב המערכת — אחרי כל שינוי משמעותי הוא מתעדכן (היסטוריה + קונפיגורציה + מה פתוח).
>
> לסטטוס runtime *בזמן אמת* (deploy פעיל, ריצה אחרונה, env vars):
> ```bash
> RENDER_API_KEY=… python3 scripts/status.py
> ```

---

## מצב המערכת

| | |
|---|---|
| **שירות** | `passparto-daily-report` (Render cron) — `crn-d7ovvo0g4nts7387q580` |
| **Repo / branch** | [michaelbarg/passparto-daily-report](https://github.com/michaelbarg/passparto-daily-report) — `main` (auto-deploy on push) |
| **Region** | Oregon |
| **תזמון** | `0 3 * * *` UTC = **06:00 בבוקר ישראל** (DST). בחורף יקפוץ ל-05:00 IL כש-Israel עוברת ל-UTC+2. |
| **ערוץ שליחה** | **Resend ישיר** מ-`reports@passparto.com`. Klaviyo Flow קיים רק כ-fallback אם Resend נופל. |
| **נמען** | `MICHAEL_EMAIL` (`michael@passparto.com`) |
| **מקור הזמנות** | Shopify Admin API live, אימות OAuth `client_credentials` (טוקן `shpat_` חי כל ריצה — אין צורך בטוקן סטטי) |
| **חנות** | `1fs2bv-ut.myshopify.com` (= `www.passparto.co.il`) |

---

## מה במייל

### טבלת "הזמנות לטיפול"

7 עמודות (RTL):

```
#  |  מוצר  |  ספק  |  מידה  |  צבע  |  כמות  |  הזמנה
```

- **שורה לכל line item** — הזמנה עם 3 פריטים = 3 שורות שחולקות מספר הזמנה אחד.
- מספור סידורי רץ דרך כל הפריטים (`loop.index`).
- **מספר הזמנה הוא קישור** לעמוד ההזמנה ב-Shopify admin: `https://1fs2bv-ut.myshopify.com/admin/orders/{id}`.
- **🆕** מסומן ליד הזמנות שנפתחו ב-24 השעות האחרונות.
- **Badge בראש הסעיף**: `🆕 N חדשות מאתמול`.
- כשאין הזמנות פתוחות — מודעה ירוקה "✅ אין הזמנות פתוחות לטיפול. עבודה טובה!"

### קריטריון "הזמנה לטיפול"

```
status                = open                   (לא בוטל / לא ארכיון)
fulfillment_status    = unfulfilled             (לא partial — ממש לא יצא)
financial_status      = paid OR authorized      (כסף הועבר או מאושר לחיוב)
order number (name)   ≥ #1776                  (חתך תפעולי, ניתן לשינוי)
total_price           > 0                       (מסנן ₪0 לכל מקרה)
```

### סיווג ספק (Cotton Avenue ברירת מחדל + חוקים)

`src/supplier_rules.py`:

```python
NON_CA_PATTERNS = [
    (r"MICHSAF|מיקסף",        "MICHSAF"),
    (r"\bnaaman\b|נעמן",       "נעמן"),
    (r"\bsoltam\b|סולתם",      "סולתם"),
    (r"החלקה",                 "החלקה"),
    (r"ויסקו",                 "ויסקו"),
    (r"מארז\s*יוקרתי.*מגבות"
     r"|מארז\s*\d+\s*מגבות"
     r"|מגבות\s*\d{3}\s*ג"
     r"|מגבות.*במשקל\s*\d{3}", "מגבות יוקרתי"),
    (r"\bחשמל\b|מוצרי\s*חשמל", "חשמל"),
]
DEFAULT_SUPPLIER = "Cotton Avenue"

NAME_OVERRIDES = [
    (r"דריה",                            "סאטן 500 רקומה בזהב"),
    (r"טופר.*פספרטו|טופר\s*למזרן",       "טופר"),
]
```

הוספת חוק חדש = שורה אחת בקובץ הזה. אין סנכרון Airtable; Cotton Avenue ברירת מחדל.

### סעיפים נוספים במייל

קמפיינים אתמול · Flows אקטיביים · בסיס הלקוחות (סגמנטים) · סיכום הכנסות · תובנת AI יומית.

---

## איך מפעילים ידנית

```bash
RENDER_API_KEY=… RENDER_SERVICE_ID=crn-d7ovvo0g4nts7387q580 \
  python3 scripts/trigger_now.py
```

או ב-Render dashboard: `passparto-daily-report` ← **Trigger Run**.

ריצה אורכת 11–14 דקות (Klaviyo rate-limit מאט קריאות statistics; Shopify עצמה מהירה — 1–3 שניות).

---

## משתני סביבה

| שם | מקור | תפקיד |
|---|---|---|
| `KLAVIYO_KEY` | service-direct | קמפיינים, Flows, fallback delivery |
| `ANTHROPIC_API_KEY` | service-direct | תובנת AI יומית |
| `MICHAEL_EMAIL` | service-direct | נמען המייל |
| `KLAVIYO_PLACED_ORDER_METRIC_ID` | service-direct | חוסך metric discovery |
| `SHOPIFY_STORE_URL` | env-group `cotton-sync-secrets` | דומיין החנות |
| `SHOPIFY_ADMIN_TOKEN` | env-group `cotton-sync-secrets` | (לא נחוץ; OAuth מתעדף) |
| `SHOPIFY_CLIENT_ID` | env-group `cotton-sync-secrets` | OAuth client_credentials |
| `SHOPIFY_CLIENT_SECRET` | env-group `cotton-sync-secrets` | OAuth client_credentials |
| `RESEND_API_KEY` | env-group `cotton-sync-secrets` | שליחת המייל |
| `SHOPIFY_MIN_ORDER_NUMBER` | (אופציונלי, default 1776) | חתך מספר התחלה |
| `UNFULFILLED_MAX_IN_EMAIL` | (אופציונלי, default 100) | חיתוך לטבלה |
| `REPORT_FROM_EMAIL` | (אופציונלי, default `reports@passparto.com`) | from |

---

## מה פתוח

- [ ] **סיבוב סודות שנחשפו בצ'אט** (לא דחוף — תלות פנימית בלבד):
  - `RENDER_API_KEY` ([dashboard](https://dashboard.render.com/u/settings#api-keys))
  - `KLAVIYO_KEY` (Klaviyo: Profile → Account → API Keys)
  - `ANTHROPIC_API_KEY` ([Console](https://console.anthropic.com))
  - `RESEND_API_KEY` ([Resend dashboard](https://resend.com/api-keys))
  - `SHOPIFY_ADMIN_TOKEN` (Shopify admin → Apps → uninstall + reinstall)

- [ ] **לאמת את `passparto.co.il` ב-Resend** (אופציונלי) — אם תעדיף שהמייל יגיע מ-`@passparto.co.il` במקום `@passparto.com`.

- [ ] **תיקון DST** (אופציונלי, לא דחוף) — Render cron הוא UTC. כרגע `0 3 * * *` נותן 06:00 בקיץ ו-05:00 בחורף. אפשר להוסיף ל-`main.py` בדיקה שמדלגת על ריצה כשהיא לא 06:00 בישראל, או לעדכן ידנית פעמיים בשנה.

- [ ] **בדיקה אם Klaviyo שלח מייל "ההזמנה יצאה"** (סימון ירוק/אדום ליד כל הזמנה לפי האם הלקוח קיבל עדכון משלוח). תוגדר כשתבקש.

- [ ] **הוספת חוקים נוספים ל-`supplier_rules.py`** ככל שיתגלו מוצרים שמסווגים שגויים. עדכון = שורה אחת בקובץ.

---

## היסטוריה כרונולוגית

### יום 1 — 25.05.2026

| שעה (UTC) | אירוע |
|---|---|
| 09:09 | Merge PR #1: תיקון רינדור הקמפיינים/Flows + טבלת "הזמנות לטיפול" עם צ'קבוקס/כתובת. Render redeploy. |
| 09:10 | ריצה ידנית ראשונה (`job-d8a145…`) — succeeded, אבל מוצרים מ-Klaviyo events fallback (Shopify token לא תקף). |
| 09:38 | Render schedule עודכן `0 5 * * *` → `0 3 * * *` (08:00 IL → 06:00 IL DST). |
| 09:58 | PR #3: תמיכה ב-`SHOPIFY_STORE_URL` ובסודות מ-env-groups מקושרים. |
| 10:32 | PR #4: שליחה ישירה דרך Resend, Jinja2 templating (לא Klaviyo Flow). |
| 10:51 | PR #5: תיקון from-domain ל-`reports@passparto.com` (passparto.co.il לא מאומת ב-Resend). |
| 11:05 | ✅ **מייל ראשון שנמסר דרך Resend** — `a2e49a91…`, last_event=`delivered`, 0 Klaviyo events. |
| 11:38 | PR #7: מבנה טבלה חדש — שורה לכל line item, מספרי הזמנה כקישורים ל-Shopify admin, badge `🆕 חדשות מאתמול`. |
| 11:43 | PR #8: עמודת צבע נפרדת (`variant_title` מתפצל למידה+צבע). |
| 12:11 | PR #9: גילוי + יישום OAuth `client_credentials` → `shpat_` חי. החנות מאומתת: פספרטו, ILS, www.passparto.co.il. הראיתי שיש 1154 הזמנות פתוחות בכלל הזמנים, רובן legacy. |
| 12:39 | PR #10/11: סינון מדויק `status=open` + `unfulfilled` + `paid\|authorized` + `name>=#1776` → 54 הזמנות אמיתיות. |
| 12:51 | ✅ **ריצה סופית של היום** (`52fb7edd…`) עם 54 הזמנות מ-#1776 עד #2155. **🔒 נעול.** |

### יום 2 — 26.05.2026

| שעה (UTC) | אירוע |
|---|---|
| 03:11 | ✅ **ריצה אוטומטית ראשונה** (06:11 IL) — `94083fcd…`, 42 הזמנות (12 נשלחו בלילה, 1 חדשה #2156). דרך Resend. |
| 04:30 | PR #13: ניסיון להוסיף שמות Cotton Avenue + עמודת ספק דרך Airtable. **לא הצליח** — ה-`Source Type` תייג מדי הרבה מוצרים כ-"אחר". |
| 04:40 | מייל ידני (`6aa6faeb…`) עם הניסיון של PR #13 — סיווג שגוי מ-Airtable. |
| 04:55 | PR #14: **רוויזיה לפי הוראות המפעיל** — Cotton Avenue ברירת מחדל, חוקי regex פר-קטגוריה (MICHSAF, נעמן, סולתם, ויסקו, החלקה, מגבות יוקרתי, חשמל), + 2 name overrides (דריה → סאטן 500 רקומה בזהב; טופר פספרטו → טופר). |
| 04:56 | ריצה ידנית עם הקוד החדש מ-PR #14. |
| 05:14 | האחדת `STATUS.md` (PR #15). |
