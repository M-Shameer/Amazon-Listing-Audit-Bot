"""
Checks across the listings of one parent (family).

A+ content (EBC) and Brand Story are usually added to a whole parent at
once. So a listing without A+ is only a problem when ANOTHER listing of
the same parent has it:

- No listing of the parent shows A+   -> nothing is reported.
- Some listings show A+, others don't  -> the ones without it are
  reported, naming a listing that has it.

Listings are grouped by their parent ASIN (read from the page). When the
parent could not be read, all listings of the audit are one group.
Pure functions: no browser, fully unit tested.
"""

from modules.content_display import STATUS_DISPLAYED, STATUS_NOT_DISPLAYED


SECTIONS = {
    "aplus": "A+ content (EBC)",
    "brand_story": "Brand Story",
}

CHECKED_STATUSES = ("ISSUES FOUND", "NO RULE-BASED ISSUES FOUND", "COMPLETED WITH WARNINGS")


def _status(result, key):
    return ((result.get("content_display") or {}).get(key) or {}).get("status")


def group_by_parent(results):
    """{parent: [results]} for products that were checked."""

    groups = {}

    for result in results:
        if result.get("overall_status") not in CHECKED_STATUSES:
            continue
        parent = result.get("parent_asin") or "(this audit)"
        groups.setdefault(parent, []).append(result)

    # Listings whose parent was not read join the only known parent.
    known = [p for p in groups if p != "(this audit)"]
    if "(this audit)" in groups and len(known) == 1:
        groups[known[0]] += groups.pop("(this audit)")

    return groups


def apply_family_checks(results):
    """
    Add 'A+ missing' (and 'Brand Story missing') findings only where
    another listing of the same parent shows it. Changes results in place.
    """

    for parent, members in group_by_parent(results).items():

        for key, label in SECTIONS.items():

            having = [r for r in members if _status(r, key) == STATUS_DISPLAYED]

            if not having:
                continue   # no listing of this parent has it: not an error

            example = having[0].get("asin", "")

            for result in members:

                if _status(result, key) != STATUS_NOT_DISPLAYED:
                    continue

                findings = result.setdefault("content_findings", [])

                if any(f.get("Item") == label for f in findings):
                    continue

                findings.append({
                    "Item": label,
                    "Status": STATUS_NOT_DISPLAYED,
                    "Detail": f"Other listings of this parent show {label} "
                              f"(e.g. {example}), but this one does not. "
                              "Add it to this ASIN in Seller Central.",
                    "Example": example,
                })

                if result.get("overall_status") == "NO RULE-BASED ISSUES FOUND":
                    result["overall_status"] = "ISSUES FOUND"

    return results
