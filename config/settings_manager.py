
import json
import re

from pathlib import Path
from datetime import datetime


# -----------------------------------------
# PROJECT PATHS
# -----------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONFIG_DIR = PROJECT_ROOT / "config"

SETTINGS_FILE = CONFIG_DIR / "settings.json"


# -----------------------------------------
# DEFAULT APPLICATION SETTINGS
# -----------------------------------------

DEFAULT_SETTINGS = {

    "marketplace": "Amazon UK",

    "marketplace_domain": "www.amazon.co.uk",

    "delivery_country": "United Kingdom",

    "delivery_postcode": "",

    "location_saved": False,

    "amazon_location_confirmed": False,

    "amazon_location_header": "",

    "last_location_verified": None,

    "last_updated": None,

    "browser_profile": "data/amazon_uk_profile",

    # Your seller name exactly as Amazon shows it after "Sold by".
    # Used to check whether YOU hold the Featured Offer.
    "expected_seller": "",

    # Website colour mode: "light" or "dark".
    "ui_theme": "light",

    # True: audits run in an invisible Chrome (no windows, nothing in
    # the taskbar). False: the Chrome window is shown.
    "background_browser": True

}


# -----------------------------------------
# POSTCODE HELPERS
# -----------------------------------------

def normalise_postcode(postcode):
    """Remove spaces and convert postcode to uppercase."""

    return re.sub(
        r"\s+",
        "",
        str(postcode)
    ).upper()


def format_postcode(postcode):
    """Format a UK postcode with a space before its last 3 characters."""

    cleaned = normalise_postcode(postcode)

    if cleaned == "GIR0AA":
        return "GIR 0AA"

    if len(cleaned) > 3:
        return cleaned[:-3] + " " + cleaned[-3:]

    return cleaned


def is_valid_uk_postcode(postcode):
    """Perform basic UK postcode format validation."""

    cleaned = str(postcode).strip().upper()

    pattern = (
        r"^(GIR\s?0AA|[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})$"
    )

    return bool(
        re.fullmatch(pattern, cleaned)
    )


# -----------------------------------------
# READ SETTINGS
# -----------------------------------------

def load_settings():
    """
    Load saved application settings.

    If the settings file does not exist,
    return the default settings.
    """

    settings = DEFAULT_SETTINGS.copy()

    if SETTINGS_FILE.exists():

        try:

            with open(
                SETTINGS_FILE,
                "r",
                encoding="utf-8"
            ) as file:

                saved_settings = json.load(file)

            if isinstance(saved_settings, dict):

                settings.update(saved_settings)

        except (json.JSONDecodeError, OSError):

            # Keep default settings if file cannot be read
            pass

    return settings


# -----------------------------------------
# WRITE SETTINGS
# -----------------------------------------

def write_settings(settings):
    """Save settings permanently to a JSON file."""

    CONFIG_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        SETTINGS_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            settings,
            file,
            indent=4,
            ensure_ascii=False
        )


# -----------------------------------------
# SAVE DELIVERY POSTCODE
# -----------------------------------------

def save_delivery_postcode(postcode):
    """
    Save the default Amazon UK delivery postcode.

    If the postcode changes, Amazon location
    verification must be performed again.
    """

    postcode = str(postcode).strip().upper()

    if not is_valid_uk_postcode(postcode):

        raise ValueError(
            "Please enter a valid UK postcode."
        )

    formatted = format_postcode(postcode)

    settings = load_settings()

    old_postcode = settings.get(
        "delivery_postcode",
        ""
    )

    # Check whether the postcode has changed
    if (
        normalise_postcode(old_postcode)
        != normalise_postcode(formatted)
    ):

        settings["amazon_location_confirmed"] = False

        settings["amazon_location_header"] = ""

        settings["last_location_verified"] = None

    settings["delivery_postcode"] = formatted

    settings["location_saved"] = True

    settings["last_updated"] = (
        datetime.now().astimezone().isoformat()
    )

    write_settings(settings)

    return settings


# -----------------------------------------
# CONFIRM AMAZON LOCATION
# -----------------------------------------

def mark_location_verified(postcode, amazon_header):
    """
    Mark location verified only when the postcode
    saved in the application matches Amazon's header.
    """

    settings = load_settings()

    saved_postcode = settings.get(
        "delivery_postcode",
        ""
    )

    expected = normalise_postcode(
        saved_postcode
    )

    supplied = normalise_postcode(
        postcode
    )

    header = normalise_postcode(
        amazon_header
    )

    if not expected or expected != supplied:

        return False

    if expected not in header:

        settings["amazon_location_confirmed"] = False

        write_settings(settings)

        return False

    settings["amazon_location_confirmed"] = True

    settings["amazon_location_header"] = amazon_header

    settings["last_location_verified"] = (
        datetime.now().astimezone().isoformat()
    )

    write_settings(settings)

    return True


# -----------------------------------------
# SAVE YOUR SELLER NAME
# -----------------------------------------

def save_expected_seller(seller_name):
    """
    Save your seller name (as shown after "Sold by" on Amazon).
    An empty name is allowed: it switches the ownership check off.
    """

    name = re.sub(r"\s+", " ", str(seller_name or "")).strip()

    if len(name) > 80:

        raise ValueError(
            "The seller name is too long (80 characters maximum)."
        )

    settings = load_settings()

    settings["expected_seller"] = name

    settings["last_updated"] = (
        datetime.now().astimezone().isoformat()
    )

    write_settings(settings)

    return settings


# -----------------------------------------
# SAVE WEBSITE THEME (light / dark)
# -----------------------------------------

def save_ui_theme(mode):
    """Save the website colour mode. Only "light" or "dark" is accepted."""

    if mode not in ("light", "dark"):
        raise ValueError("Theme must be 'light' or 'dark'.")

    settings = load_settings()

    settings["ui_theme"] = mode

    write_settings(settings)

    return settings


# -----------------------------------------
# SAVE BROWSER MODE (background / visible)
# -----------------------------------------

def save_background_browser(enabled):
    """Save whether audits run in an invisible (background) Chrome."""

    settings = load_settings()

    settings["background_browser"] = bool(enabled)

    write_settings(settings)

    return settings


# -----------------------------------------
# CLEAR SAVED LOCATION
# -----------------------------------------

def clear_delivery_location():
    """Remove the saved delivery postcode."""

    settings = load_settings()

    settings["delivery_postcode"] = ""

    settings["location_saved"] = False

    settings["amazon_location_confirmed"] = False

    settings["amazon_location_header"] = ""

    settings["last_location_verified"] = None

    settings["last_updated"] = (
        datetime.now().astimezone().isoformat()
    )

    write_settings(settings)

    return settings
