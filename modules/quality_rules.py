"""
Listing quality rules (pure functions, no browser).

Checks the title, bullet points, description and images read from the
live Amazon UK page against Amazon's published listing rules:

- Titles: at most 200 characters including spaces; the characters
  ! $ ? _ { } ^ ¬ ¦ are not allowed unless part of the brand name;
  no promotional phrases; the same word should not be repeated
  more than twice.
- Bullet points: at least 3; no special characters such as
  ™ ® © € … † ‡ ¢ £ ¥ ± ~ ; no emojis; no refund guarantees,
  contact details, ASINs or placeholders such as "N/A" or "TBD".

Every finding is a dictionary:
    {"area", "rule", "found", "expected", "severity", "action"}

severity:
    "High"   - breaks an Amazon rule; Amazon may rewrite or suppress it.
    "Medium" - weakens the listing; should be fixed.
    "Low"    - small style problem.
    "Advice" - a recommendation, not a rule.
"""

import re


TITLE_MAX = 200
TITLE_MOBILE = 80
BULLET_MIN_COUNT = 3
BULLET_MIN_LENGTH = 10
BULLET_MAX_LENGTH = 255

# Project rule: a listing should show at least this many images.
RECOMMENDED_MIN_IMAGES = 6

TITLE_BANNED_CHARS = "!$?_{}^¬¦"

BULLET_BANNED_CHARS = "™®©€…†‡¢£¥±~"

# Emojis and decorative symbols (✅ ❌ ★ ☺ etc.).
EMOJI_PATTERN = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF"
    "\U00002B00-\U00002BFF\U0000FE0F]"
)

PROMO_PHRASES = [
    "free shipping", "free delivery", "best seller", "bestseller",
    "best-seller", "hot sale", "on sale", "cheapest", "lowest price",
    "100% quality", "top rated", "limited offer", "buy now", "discount",
]

GUARANTEE_PHRASES = [
    "full refund", "money back", "money-back", "refund guarantee",
    "if not satisfied", "unconditional guarantee", "100% satisfaction",
    "satisfaction guaranteed",
]

PLACEHOLDER_PATTERN = re.compile(
    r"\b(?:n/a|not applicable|tbd|to be decided|yet to decide|copy pending)\b",
    re.IGNORECASE
)

CONTACT_PATTERN = re.compile(
    r"(?:https?://|www\.|\b[\w.+-]+@[\w-]+\.[\w.]+\b)",
    re.IGNORECASE
)

ASIN_PATTERN = re.compile(r"\bB0[A-Z0-9]{8}\b")

# Small words that may repeat in a title.
SMALL_WORDS = {
    "a", "an", "the", "and", "or", "for", "of", "with", "in", "on",
    "to", "by", "at", "from", "x", "&", "-", "cm", "set", "pack",
}


def _finding(area, rule, found, expected, severity, action):

    return {
        "area": area,
        "rule": rule,
        "found": found,
        "expected": expected,
        "severity": severity,
        "action": action,
    }


def _short(text, limit=90):
    """Shorten long text for display."""

    text = str(text or "").strip()

    return text if len(text) <= limit else text[:limit - 1] + "…"


def _phrases_in(text, phrases):

    lower = text.lower()

    return [phrase for phrase in phrases if phrase in lower]


def check_title(title):
    """Check the product title. Returns a list of findings."""

    findings = []

    title = (title or "").strip()

    if not title:
        return [_finding(
            "Title", "Title not found", "(empty)", "A product title",
            "High", "Check the page loaded fully; then check the title in Seller Central."
        )]

    length = len(title)

    if length > TITLE_MAX:
        findings.append(_finding(
            "Title", "Title too long", f"{length} characters",
            f"{TITLE_MAX} characters or fewer", "High",
            "Shorten the title; Amazon may rewrite or suppress it."
        ))
    elif length > TITLE_MOBILE:
        findings.append(_finding(
            "Title", "Title longer than mobile view", f"{length} characters",
            f"About {TITLE_MOBILE} characters show on mobile", "Advice",
            "Put brand, product type, size and colour in the first 80 characters."
        ))

    banned = sorted({char for char in title if char in TITLE_BANNED_CHARS})

    if banned:
        findings.append(_finding(
            "Title", "Special characters not allowed", " ".join(banned),
            "None of ! $ ? _ { } ^ ¬ ¦ (unless part of the brand name)", "High",
            "Remove these characters from the title."
        ))

    promos = _phrases_in(title, PROMO_PHRASES)

    if promos:
        findings.append(_finding(
            "Title", "Promotional wording", ", ".join(promos),
            "No promotional or price wording", "High",
            "Remove promotional phrases from the title."
        ))

    words = re.findall(r"[a-z0-9]+", title.lower())

    counts = {}

    for word in words:
        if word not in SMALL_WORDS and not word.isdigit() and len(word) > 2:
            counts[word] = counts.get(word, 0) + 1

    repeated = sorted(word for word, count in counts.items() if count > 2)

    if repeated:
        findings.append(_finding(
            "Title", "Word repeated more than twice",
            ", ".join(f"{word} ×{counts[word]}" for word in repeated),
            "Each word at most twice", "Medium",
            "Remove the repeated keywords."
        ))

    if EMOJI_PATTERN.search(title):
        findings.append(_finding(
            "Title", "Emoji or symbol in title", _short(title),
            "Plain text only", "High", "Remove emojis and decorative symbols."
        ))

    return findings


def check_bullets(bullets):
    """Check the bullet points ("About this item")."""

    findings = []

    bullets = [str(bullet).strip() for bullet in (bullets or []) if str(bullet).strip()]

    if len(bullets) < BULLET_MIN_COUNT:
        findings.append(_finding(
            "Bullet points", "Too few bullet points", f"{len(bullets)} bullet(s)",
            f"At least {BULLET_MIN_COUNT} (5 recommended)", "Medium",
            "Add bullet points describing the key features."
        ))

    seen = {}

    for number, bullet in enumerate(bullets, start=1):

        area = f"Bullet {number}"

        banned = sorted({char for char in bullet if char in BULLET_BANNED_CHARS})

        if banned:
            findings.append(_finding(
                area, "Special characters not allowed", " ".join(banned),
                "None of ™ ® © € … † ‡ ¢ £ ¥ ± ~", "High",
                "Remove these characters; Amazon may rewrite the bullet."
            ))

        emojis = EMOJI_PATTERN.findall(bullet)

        if emojis:
            findings.append(_finding(
                area, "Emoji or decorative symbol", " ".join(sorted(set(emojis))),
                "No emojis", "High", "Remove the emojis."
            ))

        guarantees = _phrases_in(bullet, GUARANTEE_PHRASES)

        if guarantees:
            findings.append(_finding(
                area, "Refund or guarantee wording", ", ".join(guarantees),
                "No refund or guarantee claims", "High",
                "Remove the guarantee wording."
            ))

        if CONTACT_PATTERN.search(bullet):
            findings.append(_finding(
                area, "Website, email or contact details", _short(bullet),
                "No links or contact details", "High", "Remove links and contact details."
            ))

        if ASIN_PATTERN.search(bullet):
            findings.append(_finding(
                area, "ASIN in bullet point", ASIN_PATTERN.search(bullet).group(0),
                "No ASIN numbers", "High", "Remove the ASIN."
            ))

        placeholder = PLACEHOLDER_PATTERN.search(bullet)

        if placeholder:
            findings.append(_finding(
                area, "Placeholder text", placeholder.group(0),
                "Real product information", "High", "Replace the placeholder with real text."
            ))

        if len(bullet) < BULLET_MIN_LENGTH:
            findings.append(_finding(
                area, "Bullet point too short", _short(bullet),
                f"At least {BULLET_MIN_LENGTH} characters", "Low",
                "Write a full feature description."
            ))
        elif len(bullet) > BULLET_MAX_LENGTH:
            findings.append(_finding(
                area, "Bullet point long", f"{len(bullet)} characters",
                f"About {BULLET_MAX_LENGTH} characters or fewer (check your category)", "Advice",
                "Shorten it so customers read it fully."
            ))

        first_letter = re.search(r"[A-Za-z]", bullet)

        if first_letter and first_letter.group(0).islower() and first_letter.start() == 0:
            findings.append(_finding(
                area, "Does not start with a capital letter", _short(bullet, 40),
                "Start with a capital letter", "Low", "Capitalise the first word."
            ))

        key = re.sub(r"\W+", "", bullet.lower())

        if key in seen:
            findings.append(_finding(
                area, "Duplicate bullet point", f"Same as bullet {seen[key]}",
                "Each bullet unique", "Medium", "Replace it with a different feature."
            ))
        else:
            seen[key] = number

    return findings


def check_description(description, aplus_displayed):
    """A listing needs a description unless A+ content replaces it."""

    if (description or "").strip() or aplus_displayed:
        return []

    return [_finding(
        "Description", "No product description and no A+ content", "(empty)",
        "A product description or A+ content", "Medium",
        "Add a product description or A+ content in Seller Central."
    )]


def check_images(image_count):
    """Recommend enough listing images. image_count None = not read."""

    if image_count is None:
        return []

    if image_count == 0:
        return [_finding(
            "Images", "No listing images found", "0 images",
            "Main image plus extra images", "High",
            "Check the images in Seller Central."
        )]

    if image_count < RECOMMENDED_MIN_IMAGES:
        return [_finding(
            "Images", "Few listing images", f"{image_count} image(s)",
            f"{RECOMMENDED_MIN_IMAGES} or more (project rule)", "Advice",
            "Add lifestyle, size and detail images."
        )]

    return []


def check_listing_quality(content, image_count=None, aplus_displayed=False):
    """Run every quality rule on one product's listing content."""

    content = content or {}

    findings = []

    findings += check_title(content.get("title"))
    findings += check_bullets(content.get("bullets"))
    findings += check_description(content.get("description"), aplus_displayed)
    findings += check_images(image_count)

    return findings
