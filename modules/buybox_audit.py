"""
Buy Box / Featured Offer audit.

Reads the purchase area of an Amazon UK product page, but only after
the session module confirms Amazon is using the saved delivery postcode.

On Amazon, the offer shown in the purchase box with "Add to Basket" is
the Featured Offer for that delivery location at that moment. So when
the location is verified, the buttons are visible and the seller name
is read, the app can say WHO holds the Featured Offer. If you save your
own seller name (Delivery Location page), it also says whether YOU hold it.

Safety rules:
- Never clicks Add to Basket, Buy Now or any other offer button.
- Never bypasses CAPTCHA or other Amazon security checks.
- A value that was not read is left empty and reported as NOT VERIFIED.

The reading logic (parse_seller_and_dispatch) and the decision logic
(classify_featured_offer) are plain functions with no browser, so they
are covered by tests/test_buybox.py.
"""

import re
import json
from datetime import datetime
from pathlib import Path

from config.settings_manager import load_settings
from modules.amazon_session import open_verified_amazon_page, clean_text


PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPORT_DIR = PROJECT_ROOT / "exports"


# =========================================
# SELECTORS (first match wins)
# =========================================

BUY_BOX_CONTAINERS = [
    "#desktop_buybox",
    "#buybox",
    "#tabular-buybox"
]

ADD_TO_BASKET_SELECTORS = [
    "#add-to-cart-button",
    'input[name="submit.add-to-cart"]'
]

BUY_NOW_SELECTORS = [
    "#buy-now-button",
    'input[name="submit.buy-now"]'
]

# Shown instead of Add to Basket when no offer wins the Buy Box.
SEE_ALL_OPTIONS_SELECTORS = [
    "#buybox-see-all-buying-choices",
    "#buybox-see-all-buying-choices-announce",
    '#desktop_buybox a[href*="/gp/offer-listing/"]'
]

PRICE_SELECTORS = [
    "#corePrice_feature_div .a-offscreen",
    "#corePriceDisplay_desktop_feature_div .a-offscreen",
    "#price_inside_buybox",
    ".a-price .a-offscreen"
]

# Amazon's own "Sold by" and "Dispatches from" rows in the purchase box.
SELLER_SELECTORS = [
    "#merchantInfoFeature_feature_div .offer-display-feature-text-message",
    "#sellerProfileTriggerId"
]

DISPATCH_SELECTORS = [
    "#fulfillerInfoFeature_feature_div .offer-display-feature-text-message"
]

AVAILABILITY_SELECTORS = [
    "#availability"
]

DELIVERY_SELECTORS = [
    "#mir-layout-DELIVERY_BLOCK",
    "#deliveryBlockMessage",
    "#deliveryBlock_feature_div"
]

OTHER_OFFERS_SELECTORS = [
    "#dynamic-aod-ingress-box",
    "#olp_feature_div"
]


# =========================================
# SHORT VERDICTS (one word or phrase for tables)
# =========================================

VERDICT_YOURS = "HELD BY YOUR SELLER"
VERDICT_LOST = "HELD BY ANOTHER SELLER"
VERDICT_HELD = "HELD"                      # seller known, your name not saved
VERDICT_NONE = "NO FEATURED OFFER"
VERDICT_NOT_VERIFIED = "NOT VERIFIED"
VERDICT_BLOCKED = "BLOCKED"


# =========================================
# PAGE HELPERS (need a browser page)
# =========================================

def first_visible_text(page, selectors):
    """
    Return (text, selector) for the first visible matching element
    that has text. Returns ("", "") if nothing was found.
    """

    for selector in selectors:

        try:

            locator = page.locator(selector)

            for index in range(min(locator.count(), 5)):

                element = locator.nth(index)

                if element.is_visible():

                    text = clean_text(
                        element.inner_text(timeout=3000)
                    )

                    if text:
                        return text, selector

        except Exception:
            continue

    return "", ""


def first_visible_selector(page, selectors):
    """Return the first selector with a visible element, or ""."""

    for selector in selectors:

        try:

            locator = page.locator(selector)

            for index in range(min(locator.count(), 5)):

                if locator.nth(index).is_visible():
                    return selector

        except Exception:
            continue

    return ""


# =========================================
# PURE TEXT HELPERS (no browser, unit tested)
# =========================================

# Words that start the next row of the purchase box. A seller or
# dispatch name ends where one of these begins.
_STOP_WORDS = (
    r"Dispatches|Ships|Delivery|Sold|Fulfilled|Returns|Returnable|Secure|Payment|"
    r"Gift|Legal|Packaging|Add to|Buy Now|See more|Quantity|Customer|Details"
)

# A full stop only ends a name when a space or the end follows it,
# so "Amazon.co.uk" stays whole but "Northwind." becomes "Northwind".
_END = r"(?=\s+(?:" + _STOP_WORDS + r")\b|\s*[,;|]|\.(?:\s|$)|\s*$)"


def _search(pattern, text):
    """Return group 1 of the first case-insensitive match, cleaned."""

    match = re.search(pattern, text, flags=re.IGNORECASE)

    if match:
        return clean_text(match.group(1)).strip(" .,;:")

    return ""


def parse_seller_and_dispatch(text):
    """
    Read the seller and dispatch source from purchase-box text.

    Handles Amazon's usual wordings:
      "Dispatches from Amazon  Sold by Northwind"
      "Ships from Amazon  Sold by Northwind"
      "Delivery Managed by Amazon  Sold by Northwind"
      "Dispatches from and sold by Amazon"
      "Sold by Northwind and Fulfilled by Amazon."

    Returns a dictionary:
      seller, dispatches_from, dispatch_wording
    Missing values are "".
    """

    text = clean_text(text or "")

    result = {
        "seller": "",
        "dispatches_from": "",
        "dispatch_wording": ""
    }

    if not text:
        return result

    # 1. "Dispatches from and sold by X": one company does both.
    both = _search(
        r"(?:Dispatches|Ships) from and sold by\s+(.+?)" + _END,
        text
    )

    if both:
        result["seller"] = both
        result["dispatches_from"] = both
        result["dispatch_wording"] = "Dispatches from and sold by"
        return result

    # 2. "Sold by X", optionally followed by "and Fulfilled by Amazon".
    seller = _search(r"Sold by\s+(.+?)" + _END, text)

    fulfilled = _search(
        r"Sold by\s+.+?\s+and Fulfilled by\s+(.+?)" + _END,
        text
    )

    if seller.lower().endswith(" and"):
        seller = seller[:-4].strip()

    result["seller"] = seller

    # 3. Dispatch source, in Amazon's different wordings.
    for wording in ["Dispatches from", "Ships from", "Delivery Managed by"]:

        value = _search(re.escape(wording) + r"\s+(.+?)" + _END, text)

        if value:
            result["dispatches_from"] = value
            result["dispatch_wording"] = wording
            return result

    if fulfilled:
        result["dispatches_from"] = fulfilled
        result["dispatch_wording"] = "Fulfilled by"

    return result


# Company endings that Amazon often leaves out of the "Sold by" name.
_COMPANY_ENDINGS = r"(?:\s+(?:ltd|limited|llp|plc|llc|inc|co|company|uk|gb))+\.?$"


def normalise_seller(name):
    """
    Make seller names comparable: lower-case, company endings such as
    "Ltd" or "Limited" removed, then punctuation and spaces removed.
    So "Northwind", "Northwind LTD" and "northwind." compare as the same seller.
    """

    text = re.sub(r"[^a-z0-9 ]", " ", str(name or "").lower())

    text = re.sub(r"\s+", " ", text).strip()

    text = re.sub(_COMPANY_ENDINGS, "", text)

    return text.replace(" ", "")


def detect_currency(price):
    """Return the currency code for a displayed price, or ""."""

    price = str(price or "").strip()

    if price.startswith("£"):
        return "GBP"

    if price.startswith("€"):
        return "EUR"

    if price.startswith("$"):
        return "USD"

    if price.upper().startswith("PKR"):
        return "PKR"

    return ""


def classify_featured_offer(report, expected_seller=""):
    """
    Decide the Buy Box and Featured Offer status from facts already read.

    Uses only these report keys:
      location.verified, location.security_challenge,
      purchase_area_found, add_to_basket_visible, buy_now_visible,
      see_all_buying_options_visible, availability, seller, currency

    Returns a dictionary:
      buy_box_status          long text for reports
      featured_offer_status   long text for reports
      featured_offer_verdict  short value for tables (see VERDICT_*)
      featured_offer_holder   seller name, or ""
    """

    location = report.get("location") or {}

    seller = report.get("seller", "")

    has_buttons = (
        report.get("add_to_basket_visible")
        or report.get("buy_now_visible")
    )

    availability = str(report.get("availability", "")).lower()

    def answer(buy_box_status, featured_status, verdict, holder=""):
        return {
            "buy_box_status": buy_box_status,
            "featured_offer_status": featured_status,
            "featured_offer_verdict": verdict,
            "featured_offer_holder": holder
        }

    # A. Amazon showed a security page. Nothing on it can be trusted.
    if location.get("security_challenge"):
        return answer(
            "BLOCKED - AMAZON SECURITY CHECK",
            "NOT VERIFIED - Amazon showed a security check; it was not bypassed",
            VERDICT_BLOCKED
        )

    # B. Wrong delivery location: price and offer may belong elsewhere.
    if not location.get("verified"):
        return answer(
            "NOT VERIFIED - AMAZON LOCATION NOT CONFIRMED",
            "NOT VERIFIED - Amazon is not using the saved postcode",
            VERDICT_NOT_VERIFIED
        )

    # C. A non-UK currency means the page is not showing UK offers.
    currency = report.get("currency", "")

    if currency and currency != "GBP":
        return answer(
            f"NOT VERIFIED - PRICE SHOWN IN {currency}, NOT GBP",
            "NOT VERIFIED - the page is not showing UK pricing",
            VERDICT_NOT_VERIFIED
        )

    # D. No purchase buttons: work out why, if the page says so.
    if not has_buttons:

        if report.get("see_all_buying_options_visible"):
            return answer(
                "NO BUY BOX - ONLY 'SEE ALL BUYING OPTIONS' SHOWN",
                "NO FEATURED OFFER - no offer is winning the Buy Box "
                "for this postcode (Buy Box suppressed or not awarded)",
                VERDICT_NONE
            )

        if "currently unavailable" in availability:
            return answer(
                "NO BUY BOX - PRODUCT CURRENTLY UNAVAILABLE",
                "NO FEATURED OFFER - Amazon shows the product as currently unavailable",
                VERDICT_NONE
            )

        if not report.get("purchase_area_found"):
            return answer(
                "NOT VERIFIED - PURCHASE AREA NOT DETECTED",
                "NOT VERIFIED - the purchase area could not be read",
                VERDICT_NOT_VERIFIED
            )

        return answer(
            "NOT VERIFIED - PURCHASE BUTTONS NOT DETECTED",
            "NOT VERIFIED - purchase area found but no purchase buttons were detected",
            VERDICT_NOT_VERIFIED
        )

    # E. Buttons visible but seller not read.
    if not seller:
        return answer(
            "PARTIALLY VERIFIED - PURCHASE BUTTONS VISIBLE, SELLER NOT READ",
            "NOT VERIFIED - a Featured Offer is shown but the seller name was not read",
            VERDICT_NOT_VERIFIED
        )

    # F. Buttons and seller visible: the Featured Offer holder is known.
    buy_box_status = "VERIFIED - FEATURED OFFER SHOWN WITH SELLER"

    if not expected_seller:
        return answer(
            buy_box_status,
            f"VERIFIED - Featured Offer held by {seller}. Save your seller "
            "name on the Delivery Location page to check ownership.",
            VERDICT_HELD,
            seller
        )

    if normalise_seller(seller) == normalise_seller(expected_seller):
        return answer(
            buy_box_status,
            f"VERIFIED - Featured Offer held by your seller ({seller})",
            VERDICT_YOURS,
            seller
        )

    return answer(
        buy_box_status,
        f"LOST - Featured Offer held by {seller}, not by your seller "
        f"({expected_seller})",
        VERDICT_LOST,
        seller
    )


# =========================================
# MAIN AUDIT (opens the browser)
# =========================================

def read_buy_box_from_page(page, location_report, expected_seller=""):
    """
    Read the purchase area from a page that is already open.

    Kept separate from audit_buy_box() so a later step can read the
    Buy Box and the listing text from ONE browser visit.
    """

    report = {
        "checked_at": datetime.now().astimezone().isoformat(),
        "location": location_report,
        "expected_seller": expected_seller,
        "purchase_area_found": False,
        "purchase_area_evidence": "",
        "add_to_basket_visible": False,
        "buy_now_visible": False,
        "see_all_buying_options_visible": False,
        "price": "",
        "currency": "",
        "seller": "",
        "dispatches_from": "",
        "dispatch_wording": "",
        "availability": "",
        "delivery_text": "",
        "other_offers_text": "",
        "evidence_selectors": {},
        "buy_box_status": "NOT VERIFIED",
        "featured_offer_status": "NOT VERIFIED",
        "featured_offer_verdict": VERDICT_NOT_VERIFIED,
        "featured_offer_holder": ""
    }

    # Only read the page when Amazon is using the saved postcode.
    if location_report.get("verified") and not location_report.get("security_challenge"):

        evidence = report["evidence_selectors"]

        purchase_text, evidence["purchase_area"] = first_visible_text(
            page, BUY_BOX_CONTAINERS
        )

        report["purchase_area_found"] = bool(purchase_text)
        report["purchase_area_evidence"] = purchase_text[:600]

        # Detect buttons only. Never click them.
        evidence["add_to_basket"] = first_visible_selector(page, ADD_TO_BASKET_SELECTORS)
        evidence["buy_now"] = first_visible_selector(page, BUY_NOW_SELECTORS)
        evidence["see_all_buying_options"] = first_visible_selector(
            page, SEE_ALL_OPTIONS_SELECTORS
        )

        report["add_to_basket_visible"] = bool(evidence["add_to_basket"])
        report["buy_now_visible"] = bool(evidence["buy_now"])
        report["see_all_buying_options_visible"] = bool(
            evidence["see_all_buying_options"]
        )

        report["price"], evidence["price"] = first_visible_text(page, PRICE_SELECTORS)
        report["currency"] = detect_currency(report["price"])

        report["availability"], evidence["availability"] = first_visible_text(
            page, AVAILABILITY_SELECTORS
        )

        report["delivery_text"], evidence["delivery"] = first_visible_text(
            page, DELIVERY_SELECTORS
        )

        report["other_offers_text"], evidence["other_offers"] = first_visible_text(
            page, OTHER_OFFERS_SELECTORS
        )

        # Seller: Amazon's own "Sold by" row first, then the box text.
        seller_text, seller_selector = first_visible_text(page, SELLER_SELECTORS)

        parsed = parse_seller_and_dispatch(purchase_text)

        if seller_text:
            report["seller"] = seller_text
            evidence["seller"] = seller_selector
        elif parsed["seller"]:
            report["seller"] = parsed["seller"]
            evidence["seller"] = "purchase area text"

        # Dispatch: Amazon's own "Dispatches from" row first, then the box text.
        dispatch_text, dispatch_selector = first_visible_text(page, DISPATCH_SELECTORS)

        if dispatch_text:
            report["dispatches_from"] = dispatch_text
            report["dispatch_wording"] = parsed["dispatch_wording"] or "Dispatches from"
            evidence["dispatches_from"] = dispatch_selector
        elif parsed["dispatches_from"]:
            report["dispatches_from"] = parsed["dispatches_from"]
            report["dispatch_wording"] = parsed["dispatch_wording"]
            evidence["dispatches_from"] = "purchase area text"

    report.update(classify_featured_offer(report, expected_seller))

    return report


def audit_buy_box(product_url, expected_seller=None):
    """
    Audit the purchase area of one Amazon UK product page.

    expected_seller: your seller name. If None, the name saved in
    config/settings.json is used. An empty name still reports who
    holds the Featured Offer, but cannot say whether it is yours.
    """

    if expected_seller is None:
        expected_seller = load_settings().get("expected_seller", "")

    with open_verified_amazon_page(product_url) as (page, location_report):

        report = read_buy_box_from_page(page, location_report, expected_seller)

    report["product_url"] = product_url

    return report


def save_report(report):
    """Save the Buy Box report as JSON."""

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    report_path = EXPORT_DIR / "buybox_report.json"

    with open(report_path, "w", encoding="utf-8") as file:

        json.dump(
            report,
            file,
            indent=4,
            ensure_ascii=False
        )

    return report_path


if __name__ == "__main__":

    print("\n==========================================")
    print(" AMAZON UK BUY BOX AUDIT")
    print("==========================================")

    url = input(
        "\nEnter Amazon UK product URL: "
    ).strip()

    if not url.startswith("https://www.amazon.co.uk/"):

        print("\nPlease enter a valid Amazon UK product URL.")

    else:

        result = audit_buy_box(url)

        path = save_report(result)

        print("\n========== BUY BOX REPORT ==========")

        for key, value in result.items():

            if key != "location":
                print(f"{key}: {value}")

        print("\nLocation status:", result["location"].get(
            "location_status", "")
        )

        print("\nReport saved to:", path)

        print("====================================")
