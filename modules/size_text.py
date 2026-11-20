"""
Size text consistency (pure functions, no browser).

Finds every place a size with dimensions is written on the product page
- title, bullet points, description, the "Size" field and EVERY size
button of the variation list - and checks it is written the same way:

1. The SAME size written differently, e.g.
      "King (220 x 230cm)"  in the title
      "King (220 x 230 cm)" in the Size field
   -> Medium: "Same size written differently".

2. DIFFERENT sizes written in different styles across the variations,
   e.g. "Double (200 x 200cm)" but "King (220 x 230 cm)"
   -> Low: "Sizes not written in the same style".

Spacing, brackets, the "x" sign and the unit are all compared exactly;
only capital letters are ignored.

Also gives the page's own bed dimensions in centimetres
(page_dimensions), used to check sizes printed on images.
"""

import re
from collections import Counter


SIZE_WORD = (
    r"super[\s\-]*king|s[\s.\-]?king|small[\s\-]*double|small[\s\-]*single|"
    r"single|double|king|emperor|cot[\s\-]*bed|cot|toddler|junior"
)

NUMBER = r"\d+(?:[.,]\d+)?"

UNIT = r"cm|cms|centimetres|centimeters|mm|inches|inch|in|\""

# "King (220 x 230 cm)", "King 220x230cm", "Super King - 260 x 220 cm"
SIZE_PATTERN = re.compile(
    rf"\b(?P<size>{SIZE_WORD})\b"
    rf"(?P<rest>\s*[-–:]?\s*\(?\s*(?P<a>{NUMBER})\s*[x×X]\s*(?P<b>{NUMBER})"
    rf"(?:\s*(?P<unit>{UNIT}))?(?:\s*\))?)",
    re.IGNORECASE,
)

# Any "N x N unit" (used for image text and page dimensions).
DIMENSION_PATTERN = re.compile(
    rf"(?P<a>{NUMBER})\s*[x×X]\s*(?P<b>{NUMBER})(?:\s*(?P<unit>{UNIT}))?",
    re.IGNORECASE,
)

_SIZE_NAMES = [
    (r"super[\s\-]*king|s[\s.\-]?king", "Super King"),
    (r"small[\s\-]*double", "Small Double"),
    (r"small[\s\-]*single", "Small Single"),
    (r"cot[\s\-]*bed", "Cot Bed"),
]

TO_CM = {"mm": 0.1, "inches": 2.54, "inch": 2.54, "in": 2.54, '"': 2.54}


def size_name(text):
    """Canonical size name: "SKing" -> "Super King", "double" -> "Double"."""

    lower = text.lower().strip()

    for pattern, name in _SIZE_NAMES:
        if re.fullmatch(pattern, lower):
            return name

    return lower.capitalize()


def _number(text):
    return float(str(text).replace(",", "."))


def to_cm(a, b, unit):
    """Two numbers with a unit -> (a, b) in centimetres (no unit = cm)."""

    factor = TO_CM.get((unit or "").lower(), 1.0)

    return (round(_number(a) * factor, 1), round(_number(b) * factor, 1))


def find_sizes(text):
    """
    Every size-with-dimensions in a text.
    Returns [{"written", "key", "style"}]:
      written: exactly as on the page (spaces collapsed to one)
      key:     (size name, number, number) - the same size has the same key
      style:   how it is written, sizes and numbers removed, e.g. " (N x Ncm)"
    """

    found = []

    for match in SIZE_PATTERN.finditer(str(text or "")):

        written = re.sub(r"\s+", " ", match.group(0)).strip()

        rest = re.sub(r"\s+", " ", match.group("rest")).rstrip()

        found.append({
            "written": written,
            "key": (size_name(match.group("size")),
                    _number(match.group("a")), _number(match.group("b"))),
            "style": re.sub(NUMBER, "N", rest).lower(),
        })

    return found


def collect_occurrences(content):
    """
    All sizes written on the page: [(where, size)] from the title, bullets,
    description, Size field, selected size and every size button.
    """

    content = content or {}

    sources = [("Title", content.get("title"))]

    sources += [(f"Bullet {n}", bullet) for n, bullet in enumerate(content.get("bullets") or [], start=1)]

    sources.append(("Description", content.get("description")))

    details = content.get("technical_details") or {}

    for field in ("Size", "Size Name"):
        if details.get(field):
            sources.append((f"Product information: {field}", details.get(field)))

    for name, value in (content.get("variations") or {}).items():
        if "size" in name.lower():
            sources.append(("Selected size", value))

    for option in content.get("size_options") or []:
        sources.append(("Size option", option))

    occurrences = []

    for where, text in sources:
        for size in find_sizes(text):
            occurrences.append((where, size))

    return occurrences


def _finding(rule, found, expected, severity, action):

    return {
        "area": "Size text",
        "rule": rule,
        "found": found,
        "expected": expected,
        "severity": severity,
        "action": action,
    }


def check_size_text(content):
    """All size-text consistency findings for one product."""

    occurrences = collect_occurrences(content)

    findings = []

    # 1. The same size written in more than one way.
    by_key = {}

    for where, size in occurrences:
        by_key.setdefault(size["key"], []).append((where, size))

    for key, items in by_key.items():

        writings = Counter(size["written"].lower() for _, size in items)

        if len(writings) < 2:
            continue

        common = writings.most_common(1)[0][0]

        common_written = next(size["written"] for _, size in items if size["written"].lower() == common)

        reported = set()

        for where, size in items:

            if size["written"].lower() == common or size["written"].lower() in reported:
                continue

            reported.add(size["written"].lower())

            places = sorted({w for w, s in items if s["written"].lower() == size["written"].lower()})

            findings.append(_finding(
                "Same size written differently",
                f"'{size['written']}' in {', '.join(places)}",
                f"'{common_written}' (as elsewhere on the page)",
                "Medium",
                "Write this size exactly the same way everywhere (spaces, brackets, unit)."
            ))

    # 2. Different sizes written in different styles (variation list).
    styles = {}

    for where, size in occurrences:
        if where in ("Size option", "Product information: Size", "Product information: Size Name",
                     "Selected size"):
            styles.setdefault(size["style"], size["written"])

    if len(styles) > 1:

        examples = list(styles.values())

        findings.append(_finding(
            "Sizes not written in the same style",
            " / ".join(f"'{example}'" for example in examples[1:]),
            f"Same style as '{examples[0]}'",
            "Low",
            "Use one style for every size, e.g. 'King (220 x 230 cm)'."
        ))

    return findings


def page_dimensions(content):
    """
    The bed size of THIS product in centimetres, from the Size field or
    the selected size: [(a, b)]. Empty if the page gives none.
    """

    content = content or {}

    details = content.get("technical_details") or {}

    texts = [details.get("Size"), details.get("Size Name")]
    texts += [value for name, value in (content.get("variations") or {}).items() if "size" in name.lower()]

    dimensions = []

    for text in texts:
        for match in DIMENSION_PATTERN.finditer(str(text or "")):
            pair = to_cm(match.group("a"), match.group("b"), match.group("unit"))
            if pair not in dimensions:
                dimensions.append(pair)

    return dimensions
