"""
Specification checker.

Compares Amazon's "Product information" table (technical_details) with
your own verified specification for the same product type and size.

The template column names are Amazon's field names, for example
"Item Weight" or "Thread Count". An empty cell in your template means
"do not check this field".

Results for each field:
- MATCH          the values agree (units and spacing are ignored, so
                 "1.2 kg" equals "1200 grams")
- CHECK          close but not identical, for example Amazon shows an
                 extra number or extra words; a human should look
- MISMATCH       the values disagree
- NOT SHOWN      Amazon does not show this field (not proof it is missing)

This file has no browser code, so it is fully covered by unit tests.
"""

import re


RESULT_MATCH = "MATCH"
RESULT_CHECK = "CHECK"
RESULT_MISMATCH = "MISMATCH"
RESULT_NOT_SHOWN = "NOT SHOWN ON AMAZON"

STATUS_CHECKED = "CHECKED"
STATUS_NO_SIZE = "SIZE NOT IN TEMPLATE"
STATUS_NO_AMAZON_SIZE = "AMAZON SIZE NOT READ"
STATUS_ROW_EMPTY = "TEMPLATE ROW EMPTY"


# Unit words -> (dimension, multiplier to the base unit).
# Length base unit: centimetre. Weight base unit: gram.
UNITS = {
    "mm": ("length", 0.1), "millimetre": ("length", 0.1), "millimetres": ("length", 0.1),
    "millimeter": ("length", 0.1), "millimeters": ("length", 0.1),
    "cm": ("length", 1.0), "centimetre": ("length", 1.0), "centimetres": ("length", 1.0),
    "centimeter": ("length", 1.0), "centimeters": ("length", 1.0),
    "m": ("length", 100.0), "metre": ("length", 100.0), "metres": ("length", 100.0),
    "meter": ("length", 100.0), "meters": ("length", 100.0),
    "in": ("length", 2.54), "inch": ("length", 2.54), "inches": ("length", 2.54),
    "g": ("weight", 1.0), "gram": ("weight", 1.0), "grams": ("weight", 1.0),
    "gramme": ("weight", 1.0), "grammes": ("weight", 1.0),
    "kg": ("weight", 1000.0), "kilogram": ("weight", 1000.0), "kilograms": ("weight", 1000.0),
    "kilogramme": ("weight", 1000.0), "kilogrammes": ("weight", 1000.0),
    "kilo": ("weight", 1000.0), "kilos": ("weight", 1000.0),
    "oz": ("weight", 28.3495), "ounce": ("weight", 28.3495), "ounces": ("weight", 28.3495),
    "lb": ("weight", 453.592), "lbs": ("weight", 453.592),
    "pound": ("weight", 453.592), "pounds": ("weight", 453.592),
}

# A number, optionally followed by a unit word.
_NUMBER_UNIT = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(" + "|".join(sorted(UNITS, key=len, reverse=True)) + r")?\b",
    re.IGNORECASE
)

# Field names that mean the same thing on different listings.
FIELD_ALIASES = {
    "color": "colour",
    "size name": "size",
}


def normalise_text(value):
    """Lower-case and collapse spaces. None becomes ""."""

    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip().lower()


def normalise_field(name):
    """Normalise a field name so "Item weight " matches "Item Weight"."""

    name = normalise_text(name)

    return FIELD_ALIASES.get(name, name)


def read_measure(value):
    """
    Read the numbers in a value and convert them to base units.

    "200 x 200 x 5 centimetres" -> ([200.0, 200.0, 5.0], "length")
    "1.2 kg"                    -> ([1200.0], "weight")
    "200"                       -> ([200.0], None)

    A unit written once at the end applies to the numbers before it.
    Returns (numbers, dimension). dimension is None when there are no
    units, or "mixed" when length and weight units appear together.
    """

    found = []

    for match in _NUMBER_UNIT.finditer(str(value or "")):

        number = float(match.group(1).replace(",", "."))
        unit = (match.group(2) or "").lower()

        found.append([number, unit])

    dimensions = {UNITS[unit][0] for _, unit in found if unit}

    if not dimensions:
        return [number for number, _ in found], None

    if len(dimensions) > 1:
        return [number for number, _ in found], "mixed"

    # Give unit-less numbers the next unit written after them.
    next_unit = ""

    for item in reversed(found):

        if item[1]:
            next_unit = item[1]
        else:
            item[1] = next_unit

    numbers = [
        number * UNITS[unit][1] if unit else number
        for number, unit in found
    ]

    return numbers, dimensions.pop()


def words_of(value):
    """
    The words in a value, without numbers, units and punctuation.
    "%" is kept, so "100%" and "100" are not treated as equal.
    """

    text = normalise_text(value)

    text = _NUMBER_UNIT.sub(" ", text)

    text = re.sub(r"[^a-z% ]", " ", text)

    return [word for word in text.split() if word not in ("x", "by")]


# Words that describe WHICH size, not the measurement itself, so
# "King (220 x 230 cm)" and "220 x 230 cm" are the same measurement.
SIZE_LABEL_WORDS = {
    "single", "double", "king", "super", "sking", "superking", "small", "emperor",
    "cot", "bed", "toddler", "junior", "queen", "twin", "size", "approx",
    "approximately", "each", "per",
}


# ---------------------------------------------------------
# SAME MEANING, DIFFERENT WORDING
# ---------------------------------------------------------

# Phrases written in different ways on Amazon (applied before splitting words).
_PHRASES = [
    (r"\bpillow[\s\-]*cases?\b", "pillowcase"),
    (r"\bpillow[\s\-]*slips?\b", "pillowcase"),
    (r"\bpillowcases\b", "pillowcase"),
    (r"\bquilt[\s\-]*covers?\b", "duvet cover"),
    (r"\bmicro[\s\-]*fib(?:re|er)s?\b", "microfibre"),
    (r"\bpoly[\s\-]*cotton\b", "polycotton"),
    (r"\bmachine[\s\-]*wash(?:able)?\b", "machinewash"),
    (r"\bnon[\s\-]*iron\b", "easycare"),
    (r"\beasy[\s\-]*(?:care|iron)\b", "easycare"),
    (r"\bt[\s\-]*c\b", "threadcount"),
    (r"\bthread[\s\-]*count\b", "threadcount"),
    (r"\bstripes?\b|\bstriped\b", "stripe"),
    (r"\bflorals?\b|\bflowers?\b|\bflowery\b", "floral"),
    (r"&|\+", " and "),
]

# Words that carry no meaning in a comparison.
_FILLER = {
    "and", "with", "of", "the", "a", "an", "for", "in", "on", "to", "includes",
    "include", "including", "included", "contains", "piece", "pieces", "pc",
    "pcs", "pce", "each", "approx", "approximately", "only", "is", "are",
}

# Words with the same meaning.
_SAME_WORD = {
    "grey": "grey", "gray": "grey", "multicolour": "multi", "multicoloured": "multi",
    "colour": "colour", "coloured": "colour", "premium": "premium", "luxury": "premium",
    "luxurious": "premium", "soft": "soft", "softest": "soft", "silky": "soft",
}


def meaning_words(value, drop_size_labels=False):
    """
    The words of a value reduced to their meaning: UK spelling, no plural,
    common phrases joined ("pillow cases" -> "pillowcase"), filler removed.
    "1 x Duvet Cover + 2 x Pillowcases" -> {"duvet", "cover", "pillowcase"}.
    """

    text = normalise_text(value)

    for pattern, replacement in _PHRASES:
        text = re.sub(pattern, replacement, text)

    words = set()

    for word in words_of(text):

        if drop_size_labels and word in SIZE_LABEL_WORDS:
            continue

        word = _uk_spelling(word)

        if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
            word = word[:-1]

        word = _SAME_WORD.get(word, word)

        if word and word not in _FILLER:
            words.add(word)

    return words


# British and American spellings of the same word.
_UK_US = [
    (r"fiber$", "fibre"), (r"color$", "colour"), (r"colors$", "colours"),
    (r"center$", "centre"), (r"gray$", "grey"), (r"meter$", "metre"), (r"meters$", "metres"),
    (r"liter$", "litre"), (r"liters$", "litres"), (r"ize$", "ise"), (r"ized$", "ised"),
    (r"yze$", "yse"), (r"fibers$", "fibres"), (r"favorite$", "favourite"),
]


def _squash_spelling(value):
    """Letters only, UK spelling: "Microfiber" and "micro-fibre" are equal."""
    return "".join(_uk_spelling(w) for w in re.findall(r"[a-z0-9%]+", normalise_text(value)))


def _uk_spelling(word):
    for pattern, uk in _UK_US:
        if re.search(pattern, word):
            return re.sub(pattern, uk, word)
    return word


def _close(a, b):
    return abs(a - b) <= max(0.01, 0.01 * max(abs(a), abs(b)))


def all_numbers_found(expected, actual):
    """True if every expected number appears among the actual numbers (any order)."""

    remaining = list(actual)

    for number in expected:
        match = next((other for other in remaining if _close(number, other)), None)
        if match is None:
            return False
        remaining.remove(match)

    return True


def numbers_equal(first, second):
    """Numbers are equal when they differ by less than 1 percent."""

    if len(first) != len(second):
        return False

    return all(
        abs(a - b) <= max(0.01, 0.01 * max(abs(a), abs(b)))
        for a, b in zip(first, second)
    )


def compare_value(expected, actual):
    """
    Compare one template value with one Amazon value.
    Returns (result, note).
    """

    if normalise_text(actual) == "":
        return RESULT_NOT_SHOWN, "Amazon does not show this field."

    if normalise_text(expected) == normalise_text(actual):
        return RESULT_MATCH, ""

    exp_numbers, exp_dimension = read_measure(expected)
    act_numbers, act_dimension = read_measure(actual)

    # For measurements, size names are labels, not part of the value.
    exp_words = meaning_words(expected, drop_size_labels=bool(exp_numbers))
    act_words = meaning_words(actual, drop_size_labels=bool(exp_numbers))

    same_numbers = (
        numbers_equal(exp_numbers, act_numbers)
        or numbers_equal(sorted(exp_numbers), sorted(act_numbers))
    )

    # Compare the MEANING of the words, not the exact wording.
    if exp_words and exp_words != act_words:

        if not same_numbers and exp_numbers:
            return RESULT_MISMATCH, "The words and numbers are different."

        if exp_words <= act_words:
            return RESULT_CHECK, "Same meaning; Amazon adds words."

        if act_words and act_words <= exp_words:
            return RESULT_CHECK, "Same meaning; Amazon leaves out words."

        overlap = len(exp_words & act_words) / len(exp_words | act_words)

        if overlap >= 0.75:
            return RESULT_CHECK, "Almost the same wording."

        return RESULT_MISMATCH, "The words are different."

    if exp_words and not exp_numbers:
        # Same meaning, only the wording, spelling or order differs.
        if normalise_text(expected).replace(" ", "") != normalise_text(actual).replace(" ", ""):
            if _squash_spelling(expected) != _squash_spelling(actual):
                return RESULT_CHECK, "Same meaning, different wording."
        return RESULT_MATCH, ""

    if not exp_numbers:
        # Words match (only order, spacing or punctuation differ).
        return RESULT_MATCH, ""

    if exp_dimension and act_dimension and exp_dimension != act_dimension:
        return RESULT_MISMATCH, "Different kind of unit (length vs weight)."

    if numbers_equal(exp_numbers, act_numbers):

        if (exp_dimension is None) != (act_dimension is None):
            return RESULT_CHECK, "Numbers agree, but only one side gives a unit."

        return RESULT_MATCH, ""

    if numbers_equal(sorted(exp_numbers), sorted(act_numbers)):
        return RESULT_CHECK, "Same numbers in a different order."

    # Amazon shows your numbers first, then extra ones (e.g. a depth).
    if (
        len(act_numbers) > len(exp_numbers)
        and numbers_equal(exp_numbers, act_numbers[:len(exp_numbers)])
    ):
        return RESULT_CHECK, "Amazon shows extra number(s) after your values."

    # The same measurements in another order, maybe with a depth added
    # ("King (220 x 230 cm)" vs "2.3 x 2.2 x 0.04 metres").
    if len(act_numbers) > len(exp_numbers) and all_numbers_found(exp_numbers, act_numbers):
        return RESULT_CHECK, "Same measurements; Amazon shows another order and extra number(s)."

    # "0.53 g" in the template but 530 g on Amazon: a kg / g mix-up.
    if (
        exp_dimension == "weight" and act_dimension == "weight"
        and len(exp_numbers) == 1 and len(act_numbers) == 1
        and _close(exp_numbers[0] * 1000, act_numbers[0])
    ):
        return RESULT_CHECK, "Same if your template means kg: it says grams. Write 'kg' in the template."

    return RESULT_MISMATCH, "The numbers are different."


# ---------------------------------------------------------
# VARIATION MATCHING (size + number of pieces + pack)
# ---------------------------------------------------------

# Size names, written as one word so "King" never matches "Super King".
SIZE_WORDS = {
    "single", "smallsingle", "double", "smalldouble", "king", "superking",
    "emperor", "cot", "cotbed", "toddler", "junior", "queen", "twin",
}

_SIZE_JOINS = [
    (r"\bsuper[\s\-]*king\b", "superking"),
    (r"\bs[\s.\-]*king\b", "superking"),
    (r"\bsking\b", "superking"),
    (r"\bsmall[\s\-]*double\b", "smalldouble"),
    (r"\bsmall[\s\-]*single\b", "smallsingle"),
    (r"\bcot[\s\-]*bed\b", "cotbed"),
]

_PIECES = re.compile(r"(\d+)\s*-?\s*(?:piece|pieces|pc|pcs|pce)\b")
_PACK = re.compile(r"(?:pack\s*of\s*(\d+)|(\d+)\s*-?\s*(?:pack|pk)\b|set\s*of\s*(\d+))")
_NUMBER = re.compile(r"(\d+)")


def variant_tokens(text, size_words=True):
    """
    The variation facts in a piece of text, as a set of tokens:
      size names ("double", "superking"), "pieces:4", "pack:2".
    Examples: "SKing 4 Piece" -> {"superking", "pieces:4"};
              "Double - Pack of 2" -> {"double", "pack:2"}.
    size_words=False reads only pieces and packs (used for titles).
    """

    text = str(text or "").lower()

    for pattern, word in _SIZE_JOINS:
        text = re.sub(pattern, word, text)

    tokens = set()

    if size_words:
        tokens |= {word for word in re.findall(r"[a-z]+", text) if word in SIZE_WORDS}

    tokens |= {"pieces:" + number for number in _PIECES.findall(text)}

    for groups in _PACK.findall(text):
        number = next(group for group in groups if group)
        tokens.add("pack:" + number)

    return tokens


def _first_number(value):

    match = _NUMBER.search(str(value or ""))

    return match.group(1) if match else ""


# Product information fields that describe the variation.
_VARIANT_TEXT_FIELDS = ["Size", "Size Name", "Style", "Style Name", "Pattern Name", "Configuration"]


def amazon_variant_tokens(technical_details, variant_info=None):
    """
    Everything the product page says about its size, pieces and pack:
    Product information fields, the selected variation buttons, and the
    pieces/pack wording in the title.
    """

    details = technical_details or {}
    info = variant_info or {}

    tokens = set()

    for field in _VARIANT_TEXT_FIELDS:
        tokens |= variant_tokens(details.get(field))

    for value in (info.get("selections") or {}).values():
        tokens |= variant_tokens(value)

    tokens |= variant_tokens(info.get("title"), size_words=False)

    number = _first_number(details.get("Number of Pieces"))
    if number:
        tokens.add("pieces:" + number)

    for field in ("Item Package Quantity", "Unit Count"):
        number = _first_number(details.get(field))
        if number and number != "1":
            tokens.add("pack:" + number)

    # "Number of Packs: 1" is a clear statement that this is NOT a multipack.
    for field in ("Number of Packs", "Number of Pack", "Pack Quantity", "Package Quantity"):
        number = _first_number(details.get(field))
        if number:
            tokens.add("pack:" + number)

    # "Number of Items" can mean pieces or pack, so it may confirm either.
    number = _first_number(details.get("Number of Items"))
    if number:
        tokens.add("items:" + number)

    return tokens


def _row_fits(row_tokens, amazon_tokens):
    """
    Every fact in the template row must be shown by Amazon.
    "Number of Items" may stand in for the pieces or the pack ONLY when
    Amazon does not state that fact directly (e.g. Size "Pack of 4" with
    "Number of Items: 2" is a pack of 4).
    """

    for token in row_tokens:

        if token in amazon_tokens:
            continue

        kind, _, number = token.partition(":")

        stated = any(other.startswith(kind + ":") for other in amazon_tokens)

        if kind in ("pieces", "pack") and not stated and "items:" + number in amazon_tokens:

            # When "Number of Items" equals "Number of Pieces", it is counting
            # the pieces of ONE set (duvet + pillowcase = 2), not packs.
            if kind == "pack" and "pieces:" + number in amazon_tokens:
                return False

            continue

        return False

    return True


def describe_tokens(tokens):
    """Readable text for the tokens, e.g. "Double, 4 pieces, pack of 2"."""

    sizes = sorted(token.capitalize() for token in tokens if ":" not in token)
    pieces = sorted(token.split(":")[1] + " pieces" for token in tokens if token.startswith("pieces:"))
    packs = sorted("pack of " + token.split(":")[1] for token in tokens if token.startswith("pack:"))
    items = sorted(token.split(":")[1] + " items" for token in tokens if token.startswith("items:"))

    return ", ".join(sizes + pieces + packs + items)


def find_size_row(rows, amazon_size, amazon_tokens=None):
    """
    Find the template row for this product.

    1. Variation matching: the template Size may name a size, a number
       of pieces and a pack, e.g. "Double 4 Piece" or "King Pack of 2".
       Every fact in the row must appear on Amazon's page. When several
       rows fit, the most specific one wins ("Double Pack of 2" beats
       "Double"). "King" never matches "Super King".
    2. Otherwise (Size values that name no known size, such as
       "200 x 200"): the template size must be the start of Amazon's
       size text, followed by a space or a bracket.
    """

    if amazon_tokens is None:
        amazon_tokens = variant_tokens(amazon_size)

    best, best_count = None, 0

    for row in rows:

        row_tokens = variant_tokens(row.get("size"))

        if row_tokens and _row_fits(row_tokens, amazon_tokens) and len(row_tokens) > best_count:
            best, best_count = row, len(row_tokens)

    if best is not None:
        return best

    target = normalise_text(amazon_size)

    if not target:
        return None

    for row in rows:

        size = normalise_text(row.get("size"))

        if not size or variant_tokens(row.get("size")):
            continue

        if size == target:
            return row

        if target.startswith(size) and target[len(size):len(size) + 1] in (" ", "("):

            if best is None or len(size) > len(normalise_text(best.get("size"))):
                best = row

    return best


# ---------------------------------------------------------
# TEXT CHECK COLUMNS ("Description contains", ...)
# ---------------------------------------------------------

# Template column name -> which parts of the listing are searched.
TEXT_CHECK_COLUMNS = {
    "title contains": ("title",),
    "bullets contain": ("bullets",),
    "bullet points contain": ("bullets",),
    "description contains": ("description",),
    "listing contains": ("title", "bullets", "description"),
}

_PART_NAMES = {"title": "title", "bullets": "bullet points", "description": "description"}


def text_check_parts(field):
    """The listing parts a template column searches, or () if it is a normal field."""

    return TEXT_CHECK_COLUMNS.get(normalise_text(field), ())


def _squash(text):
    """Lower case, single spaces: spelling must match, spacing and case need not."""

    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def check_text_column(expected, parts, listing):
    """
    Every phrase in the cell (separate several with ;) must appear in the
    chosen parts of the listing with the same spelling.
    Returns (result, amazon_shows, note).
    """

    listing = listing or {}

    chunks = []

    for part in parts:
        value = listing.get(part)
        chunks.append(" ".join(value) if isinstance(value, (list, tuple)) else str(value or ""))

    haystack = _squash(" ".join(chunks))

    where = " / ".join(_PART_NAMES[part] for part in parts)

    if not haystack:
        return RESULT_NOT_SHOWN, "", f"The {where} could not be read."

    phrases = [phrase.strip() for phrase in str(expected).split(";") if phrase.strip()]

    missing = [phrase for phrase in phrases if _squash(phrase) not in haystack]

    if not missing:
        return RESULT_MATCH, "Found in the " + where, ""

    return (
        RESULT_MISMATCH,
        "Not found: " + "; ".join(missing),
        f"Check the exact spelling in the {where}.",
    )


# ---------------------------------------------------------
# PARTS OF A SET written in the listing text
# (fitted sheet in a 3/4-piece duvet set, pillowcases, ...)
# ---------------------------------------------------------

# Words that say WHAT is measured, not WHICH part.
_MEASURE_WORDS = {
    "dimensions", "dimension", "size", "sizes", "width", "length", "depth",
    "height", "measurements", "measurement", "quantity", "weight",
}

_MEASURE_IN_TEXT = re.compile(
    r"\d+(?:[.,]\d+)?(?:\s*(?:" + "|".join(sorted(UNITS, key=len, reverse=True)) + r")\b)?"
    r"(?:\s*(?:x|×|by|\+)\s*\d+(?:[.,]\d+)?(?:\s*(?:"
    + "|".join(sorted(UNITS, key=len, reverse=True)) + r")\b)?)*",
    re.IGNORECASE,
)


def text_anchors(field):
    """
    Words to look for in the listing text for a template column, e.g.
      "Fitted Sheet Pocket Depth" -> ["pocket", "deep"]
      "Fitted Sheet Dimensions"   -> ["fitted sheet"]
      "Pillowcase Width"          -> ["pillowcase", "pillow case"]
    """

    name = normalise_text(field)

    if "pocket" in name:
        return ["pocket", "deep"]

    words = [word for word in re.findall(r"[a-z]+", name) if word not in _MEASURE_WORDS]

    phrase = " ".join(words)

    anchors = [phrase] if phrase else []

    if "pillowcase" in name or "pillow case" in name:
        anchors += ["pillowcase", "pillow case"]

    return list(dict.fromkeys(anchor for anchor in anchors if anchor))


def find_in_listing_text(field, expected, listing):
    """
    For a column Amazon has no field for: look for the measurement in the
    title / bullets / description near the column's words, e.g. the
    fitted sheet of a 4-piece duvet set. Returns (result, shows, note) or
    None when the text gives nothing to compare.
    """

    exp_numbers, exp_dimension = read_measure(expected)

    if not exp_numbers or not listing:
        return None

    chunks = []

    for part in ("title", "bullets", "description"):
        value = (listing or {}).get(part)
        chunks.append(" ".join(value) if isinstance(value, (list, tuple)) else str(value or ""))

    text = re.sub(r"\s+", " ", " ".join(chunks))
    lower = text.lower()

    candidates = []

    for anchor in text_anchors(field):

        for match in re.finditer(re.escape(anchor), lower):

            # Mostly AFTER the words ("fitted sheet 150 x 200 cm"), a little
            # before ("150 x 200 cm fitted sheet").
            start = max(0, match.start() - 25)
            window = text[start: match.end() + 120]
            anchor_at = match.start() - start

            for measure in _MEASURE_IN_TEXT.finditer(window):

                numbers, dimension = read_measure(measure.group(0))

                if dimension in (None, exp_dimension) and numbers and (
                    dimension or len(numbers) > 1
                ):
                    distance = measure.start() - anchor_at
                    if distance < 0:
                        distance = 1000 - distance  # before the words: less likely
                    candidates.append((measure.group(0).strip(), numbers, distance))

    if not candidates:
        return None

    for written, numbers, _ in candidates:
        if all_numbers_found(exp_numbers, numbers):
            return RESULT_MATCH, f"Listing text: '{written}'", "Found in the listing text."

    # Show the nearest measurement of the same kind (same count of numbers).
    written = sorted(
        candidates, key=lambda item: (abs(len(item[1]) - len(exp_numbers)), item[2])
    )[0][0]

    return (
        RESULT_MISMATCH,
        f"Listing text: '{written}'",
        "Amazon has no field for this; the listing text near "
        f"'{text_anchors(field)[0]}' gives a different measurement.",
    )


def find_amazon_value(technical_details, field):
    """Return (amazon_field_name, value) for a template field, or ("", "")."""

    wanted = normalise_field(field)

    for name, value in (technical_details or {}).items():

        if normalise_field(name) == wanted:
            return name, value

    return "", ""


def check_against_spec(technical_details, spec, variant_info=None):
    """
    Compare one product with the chosen specification.

    spec is a dictionary:
      {"set_name": ..., "product_type": ..., "rows": [template rows]}
    Each template row: {"product_type", "size", "values": {field: value}}

    Returns a dictionary for display, Excel and history:
      status, set_name, product_type, amazon_size, template_size,
      rows (one per checked field), counts, issues
    """

    technical_details = technical_details or {}

    selections = (variant_info or {}).get("selections") or {}

    amazon_size = (
        technical_details.get("Size")
        or technical_details.get("Size Name")
        or selections.get("size_name")
        or selections.get("size")
        or ""
    )

    amazon_tokens = amazon_variant_tokens(technical_details, variant_info)

    report = {
        "set_name": spec.get("set_name", ""),
        "product_type": spec.get("product_type", ""),
        "amazon_size": amazon_size,
        "template_size": "",
        "variant_read": describe_tokens(amazon_tokens),
        "status": STATUS_CHECKED,
        "rows": [],
        "counts": {
            RESULT_MATCH: 0,
            RESULT_CHECK: 0,
            RESULT_MISMATCH: 0,
            RESULT_NOT_SHOWN: 0
        },
        "issues": []
    }

    if not amazon_size and not amazon_tokens:
        report["status"] = STATUS_NO_AMAZON_SIZE
        return report

    row = find_size_row(spec.get("rows", []), amazon_size, amazon_tokens)

    if row is None:
        report["status"] = STATUS_NO_SIZE
        return report

    report["template_size"] = row.get("size", "")

    for field, expected in (row.get("values") or {}).items():

        if normalise_text(expected) == "":
            continue  # empty cell = do not check

        parts = text_check_parts(field)

        if parts:
            # "Description contains" etc.: search the listing text.
            amazon_field = field
            result, actual, note = check_text_column(expected, parts, variant_info)
        else:
            amazon_field, actual = find_amazon_value(technical_details, field)
            result, note = compare_value(expected, actual)

            if not amazon_field:
                # No such field on Amazon (e.g. the fitted sheet of a 4-piece
                # set): look for it in the title / bullets / description.
                found = find_in_listing_text(field, expected, variant_info)
                if found:
                    result, actual, note = found
                    parts = ("listing",)

        report["counts"][result] += 1

        report["rows"].append({
            "Field": field,
            "Your Specification": str(expected),
            "Amazon Shows": str(actual),
            "Result": result,
            "Note": note
        })

        if result == RESULT_MISMATCH:

            report["issues"].append({
                "category": "Specification Mismatch",
                "location": (
                    f"Listing text: {field}" if parts
                    else f"Product information: {amazon_field or field}"
                ),
                "detected_term": str(actual),
                "correct_term": str(expected),
                "original_text": str(actual),
                "suggested_correction": str(expected),
                "classification": "Inconsistency with your specification",
                "reason": (
                    f"Amazon shows '{actual}' but your specification "
                    f"'{report['set_name']}' (row '{report['template_size']}') says "
                    f"'{expected}'. {note}"
                ).strip()
            })

    # The size row was found, but every cell in it was empty.
    if not report["rows"]:
        report["status"] = STATUS_ROW_EMPTY

    return report
