# Passparto Daily Report — Status

> מסמך חי. מתעדכן אחרי כל שינוי משמעותי. לסטטוס בזמן-אמת על Render (ריצה אחרונה, env vars, deploy פעיל) הריצו:
> ```
> RENDER_API_KEY=... python3 scripts/status.py
> ```

## עכשיו

| | |
|---|---|
| **שירות** | `passparto-daily-report` (Render cron) |
| **תזמון** | `0 3 * * *` UTC = **06:00 בבוקר ישראל** (DST). בחורף הקרון יקפוץ ל-05:00 IL כש-Israel עוברת ל-UTC+2. |
| **Branch** | `main` (auto-deploy on push) |
| **Region** | Oregon |
| **נמען** | `MICHAEL_EMAIL` שמוגדר ב-Render |

## מה הושלם

- [x] **תיקון רינדור המייל** — הסרה של `{{ event.campaigns_html }}`/`flows_html` שמעולם לא נשלחו, החלפה ב-`{% for %}` תקין על המערכים `event.campaigns` / `event.flows`. ה"מייל לא הגיע מסודר" מפסיק.
- [x] **טבלת "הזמנות לטיפול"** בראש המייל. RTL, צ'קבוקס ויזואלי בטור הראשון, עמודת כתובת למשלוח, badges צבעוניים לפי ימים פתוחים (אדום ל-3+ ימים), שורות מתחלפות, empty-state ידידותי.
- [x] **מודול `orders_collector.py`** — מקור עיקרי Shopify Admin API, fallback ל-Klaviyo events.
- [x] **עדכון לוח זמנים ל-06:00 IL** — נכתב ב-`render.yaml` (לפריסות עתידיות) וגם ב-API ישירות על השירות הקיים.
- [x] **`scripts/trigger_now.py`** — כלי טריגר חיצוני דרך Render API.
- [x] **`scripts/status.py`** — כלי סטטוס חי שמושך מ-Render API את המצב האמיתי בכל רגע.
- [x] **PR #1 ממוזג, נפרס, ורצה ב-Render** — commit `b22b779b` הוא ה-deploy הפעיל.
- [x] **ריצה ראשונה ידנית בוצעה** — `job-d8a145p9rddc739ma0l0`, succeeded (11m 35s), 09:10–09:22 UTC ב-25.05.
- [x] **Shopify env vars מקושרים דרך env-group `cotton-sync-secrets`** — `SHOPIFY_STORE_URL` + `SHOPIFY_ADMIN_TOKEN`. הקוד מקבל את כל הוריאציות הללו (`SHOPIFY_STORE_DOMAIN` / `SHOPIFY_STORE_URL` / `SHOPIFY_DOMAIN`, ו-`SHOPIFY_ADMIN_API_TOKEN` / `SHOPIFY_ADMIN_TOKEN` / `SHOPIFY_TOKEN`), ומנקה http(s) ועריכה אם הערך הוא URL מלא.
- [x] **`status.py` מעודכן** — מציג גם משתנים שמגיעים דרך linked env-groups, כולל איזה group מספק כל אחד.
- [x] **שליחה ישירה דרך Resend (PR #4 + #5)** — עוקפת לחלוטין את Klaviyo Flow + Smart Sending. התבנית `template.html` הומרה ל-Jinja2; `src/email_payload.py` הוא מקור אמת יחיד למבנה ה-event; `src/direct_send.py` שולח דרך `https://api.resend.com/emails` מהדומיין המאומת `reports@passparto.com`. אם Resend נכשל → fallback ל-Klaviyo.
- [x] **שליחה חיה אומתה** ב-25.05.2026 11:05 UTC: id=`a2e49a91-c650-4b19-ae7d-c17ea7c22b36`, last_event=`delivered`, 0 Klaviyo events חדשים (לא נדרש fallback).

## מה פתוח

- [ ] **סיבוב סודות שנחשפו בצ'אט.** Render API החזיר את כל הסודות בערכים גלויים כשהשתמשתי ב-`RENDER_API_KEY`. כדאי לסובב:
  - `RENDER_API_KEY` ([dashboard](https://dashboard.render.com/u/settings#api-keys))
  - `KLAVIYO_KEY` (Klaviyo: Profile → Account → API Keys)
  - `ANTHROPIC_API_KEY` ([Console](https://console.anthropic.com))
  - `RESEND_API_KEY` ([Resend dashboard](https://resend.com/api-keys))
  - `SHOPIFY_ADMIN_TOKEN` (Shopify admin → Apps → uninstall + reinstall)

- [ ] **לאמת את `passparto.co.il` ב-Resend** (אופציונלי) — אם תעדיף שהמייל יגיע מ-`@passparto.co.il` במקום `@passparto.com`. אחרת, ברירת המחדל הנוכחית `reports@passparto.com` עובדת מצוין.

- [ ] **תיקון DST** (אופציונלי, לא דחוף) — Render cron הוא UTC. אפשר להוסיף ל-`main.py` בדיקה שמדלגת על ריצה כשהיא בכיוון השעון של ישראל לא 06:00, או לעדכן ידנית פעמיים בשנה. נכון לעכשיו `0 3 * * *` נותן 06:00 בקיץ ו-05:00 בחורף.

## איך מפעילים ידנית "מייל עכשיו"

```bash
RENDER_API_KEY=...   RENDER_SERVICE_ID=crn-d7ovvo0g4nts7387q580   python3 scripts/trigger_now.py
```

או ב-Render dashboard: `passparto-daily-report` ← **Trigger Run**.

## שינויים אחרונים (chronological)

- **25.05.2026 09:09 UTC** — Merge של PR #1 ל-main; Render redeploy אוטומטית; commit פעיל = `b22b779b`.
- **25.05.2026 09:10 UTC** — ריצה ידנית ראשונה דרך Render API (job-d8a145…). הסתיימה ב-`succeeded` ב-09:22.
- **25.05.2026 09:38 UTC** — Render schedule עודכן ל-`0 3 * * *` דרך API (היה `0 5 * * *`).
- **25.05.2026 09:?? UTC** — אליאסים לשמות env של Shopify (`SHOPIFY_ADMIN_TOKEN`, `SHOPIFY_TOKEN`, `SHOPIFY_DOMAIN`) + קובץ STATUS.md זה (PR #2).
- **25.05.2026 09:58 UTC** — תמיכה ב-`SHOPIFY_STORE_URL` ובסודות מ-env-groups מקושרים, `_normalize_shopify_domain()` (PR #3).
- **25.05.2026 10:32 UTC** — מסלול שליחה ישיר דרך Resend, Jinja2 instead of Klaviyo Flow (PR #4).
- **25.05.2026 10:51 UTC** — תיקון from-domain: `reports@passparto.com` (לא `support@passparto.co.il`, שלא מאומת ב-Resend) (PR #5).
- **25.05.2026 11:05 UTC** — ריצה אומתה: מייל נמסר דרך Resend (`a2e49a91-c650-4b19-ae7d-c17ea7c22b36`), Klaviyo לא הופעל. **המסלול הראשי כעת עובד end-to-end.**
