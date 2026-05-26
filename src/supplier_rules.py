"""Rule-based product classification for the daily report.

Per the operator: nearly all products in the catalogue are Cotton Avenue;
only a handful of specific brand families belong to other suppliers. The
Airtable 'Source Type' tagging proved unreliable (too many CA products
tagged as 'Other supplier'), so this module replaces it with explicit
patterns that match Shopify product titles directly.

Two responsibilities:

  1. classify_supplier(title) — returns the supplier label shown in the
     email's 'ספק' column. Default 'Cotton Avenue' unless the title
     matches one of the NON_CA_PATTERNS in order.

  2. display_product_name(title) — returns the product name to render in
     the email. By default the original Shopify title is used. The
     NAME_OVERRIDES list lets the operator map Shopify marketing titles
     to the operator-friendly Cotton catalogue names (e.g. the long
     'מצעי כותנה מצרית - דגם ד״ר דריה עם מגע של זהב' becomes
     'סאטן 500 רקומה בזהב').

Both lists are intentionally simple ordered (regex_pattern, label)
tuples so the operator can add new entries by appending lines without
needing to learn a more elaborate config format.
"""
import re


# (regex pattern, supplier label). First match wins.
NON_CA_PATTERNS = [
    (r"MICHSAF|מיקסף",                            "MICHSAF"),
    (r"\bnaaman\b|נעמן",                          "נעמן"),
    (r"\bsoltam\b|סולתם",                          "סולתם"),
    (r"החלקה",                                     "החלקה"),
    (r"ויסקו",                                     "ויסקו"),
    (r"מארז\s*יוקרתי.*מגבות"
     r"|מארז\s*\d+\s*מגבות"
     r"|מגבות\s*\d{3}\s*ג"
     r"|מגבות.*במשקל\s*\d{3}",                    "מגבות יוקרתי"),
    (r"\bחשמל\b|מוצרי\s*חשמל",                   "חשמל"),
]

DEFAULT_SUPPLIER = "Cotton Avenue"


# (regex pattern, replacement display name). First match wins.
# The Shopify marketing title gets replaced with the CA-style name only
# when the operator explicitly mapped it here.
NAME_OVERRIDES = [
    (r"דריה",                        "סאטן 500 רקומה בזהב"),
    (r"טופר.*פספרטו|טופר\s*למזרן", "טופר"),
]


def classify_supplier(shopify_title):
    s = shopify_title or ""
    for pattern, label in NON_CA_PATTERNS:
        if re.search(pattern, s, re.IGNORECASE):
            return label
    return DEFAULT_SUPPLIER


def display_product_name(shopify_title):
    s = shopify_title or ""
    for pattern, override in NAME_OVERRIDES:
        if re.search(pattern, s, re.IGNORECASE):
            return override
    return s
