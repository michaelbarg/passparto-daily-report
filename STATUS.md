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

## מה פתוח

- [ ] **שני env vars ב-Render שייתנו את ה"סריקה החיה" של Shopify:**
  - `SHOPIFY_STORE_DOMAIN` (כנראה `passparto.myshopify.com`)
  - `SHOPIFY_ADMIN_API_TOKEN` (`shpat_...`) — או באליאסים `SHOPIFY_ADMIN_TOKEN` / `SHOPIFY_TOKEN` שגם הקוד מקבל.

  עד שזה לא מוגדר, טבלת ההזמנות נבנית מ-Klaviyo events (Placed Order שלא קיבלו Fulfilled Order ב-14 הימים האחרונים) — עובד, אבל פחות מדויק מהסריקה הישירה.

- [ ] **סיבוב `RENDER_API_KEY` הקיים** — נחשף בצ'אט בריצה הראשונית. לסבב ב-https://dashboard.render.com/u/settings#api-keys.

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
