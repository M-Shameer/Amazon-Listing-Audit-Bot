"""
Link parser for pasted product lists.

Reads text copied from Excel, Google Sheets, Notepad or a browser.
It accepts any of these in any mix:
- full Amazon UK links (with or without https://, with tracking text)
- short product links such as amazon.co.uk/dp/ASIN
- bare ASINs such as B0AAAAAA01

Cells separated by tabs, commas, semicolons, spaces or new lines are
all handled. Header words and other text (for example "ASIN" or
"Colour") are ignored without an error, so a whole Excel column can
be pasted directly.
"""

import re


AMAZON_UK_PREFIX = "https://www.amazon.co.uk/"

# Maximum number of products in one run. Each product takes about
# 30 to 40 seconds, so this keeps a single run to a reasonable time.
MAX_LINKS_PER_RUN = 50

# Finds the ASIN inside a product link: /dp/ASIN or /gp/product/ASIN.
ASIN_IN_LINK = re.compile(
    r"/(?:dp|gp/product)/([A-Z0-9]{10})(?![A-Z0-9])",
    re.IGNORECASE
)

# Any of these characters separates one cell from the next.
# \s covers spaces, tabs and new lines. The others cover CSV-style text.
CELL_SEPARATORS = re.compile(r"[\s,;|]+")


def looks_like_asin(token):
    """
    True if the token looks like an Amazon ASIN.
    An ASIN is 10 letters or digits, with at least one digit and
    one letter. This avoids treating plain words such as "Colour"
    or "Duvet" as ASINs.
    """

    if not re.fullmatch(r"[A-Za-z0-9]{10}", token):
        return False

    has_digit = any(char.isdigit() for char in token)
    has_letter = any(char.isalpha() for char in token)

    return has_digit and has_letter


def extract_asin_from_link(url):
    """Return the ASIN inside an Amazon link, or "" if none is found."""

    match = ASIN_IN_LINK.search(url)

    if match:
        return match.group(1).upper()

    return ""


def parse_url_list(raw_text):
    """
    Read pasted text and return two lists:

    valid:    dictionaries with "url" and "asin", in pasted order
    rejected: dictionaries with "input" and "reason", shown to the user

    Plain words and headers are ignored silently. Only things that look
    like links or ASINs but cannot be used are reported as rejected.
    """

    valid = []
    rejected = []
    seen_asins = set()

    if not isinstance(raw_text, str):
        return valid, rejected

    # Split the whole paste into cells, then check each cell.
    for cell in CELL_SEPARATORS.split(raw_text):

        # Remove quotation marks and brackets that Excel sometimes adds.
        token = cell.strip().strip('"\'<>()[]')

        if not token:
            continue

        # CASE 1: an Amazon link (with or without https://).
        if "amazon." in token.lower():

            if token.lower().startswith("www."):
                token = "https://" + token

            if not token.lower().startswith("http"):
                token = "https://" + token

            if "amazon.co.uk" not in token.lower():

                rejected.append({
                    "input": token,
                    "reason": "Not an Amazon UK link"
                })
                continue

            asin = extract_asin_from_link(token)

            if not asin:

                rejected.append({
                    "input": token,
                    "reason": "No ASIN found in this link"
                })
                continue

            # Rebuild a clean, short link so the audit is consistent.
            clean_url = AMAZON_UK_PREFIX + "dp/" + asin

        # CASE 2: a bare ASIN, such as B0AAAAAA01.
        elif looks_like_asin(token):

            asin = token.upper()

            clean_url = AMAZON_UK_PREFIX + "dp/" + asin

                # CASE 3: a link to another website is reported, not ignored.
        elif token.lower().startswith(("http://", "https://", "www.")):

            rejected.append({
                "input": token,
                "reason": "Not an Amazon UK link"
            })
            continue

        # CASE 4: anything else (headers, notes, words) is ignored.
        else:
            continue
        # Duplicates are rejected, because the same product audited
        # twice gives the same answer and wastes time.
        if asin in seen_asins:

            rejected.append({
                "input": token,
                "reason": "Duplicate ASIN (already in this list)"
            })
            continue

        if len(valid) >= MAX_LINKS_PER_RUN:

            rejected.append({
                "input": token,
                "reason": f"Over the {MAX_LINKS_PER_RUN}-link limit per run"
            })
            continue

        seen_asins.add(asin)

        valid.append({"url": clean_url, "asin": asin})

    return valid, rejected


if __name__ == "__main__":

    # Quick self-test. Run: python -m services.link_parser
    sample = (
        "ASIN\tLink\n"
        "https://www.amazon.co.uk/Brightbed-Duvet/dp/B0AAAAAA01/ref=sr_1_17?crid=1KGM\n"
        "B0AAAAAA02\n"
        "amazon.co.uk/dp/B0AAAAAA03\n"
        "B0AAAAAA01\n"
        "https://www.google.com/x\n"
        "Colour, Size"
    )

    valid, rejected = parse_url_list(sample)

    print("VALID:")
    for item in valid:
        print(" ", item["asin"], item["url"])

    print("REJECTED:")
    for item in rejected:
        print(" ", item["input"], "->", item["reason"])