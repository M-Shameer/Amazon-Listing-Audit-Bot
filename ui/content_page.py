"""
Website section: listing images, A+ content (EBC) and Brand Story.

Presentation only. The checks live in modules/content_display.py
and modules/design_match.py.
"""

import streamlit as st

from modules.content_display import STATUS_DISPLAYED, STATUS_NOT_DISPLAYED
from modules.design_match import (
    VERDICT_SAME,
    VERDICT_DIFFERENT,
    VERDICT_UNCERTAIN,
    VERDICT_NOT_CHECKED,
    VERDICT_SKIPPED,
)


def _show_images(rows, width=160):
    """Show A+ images with '#number | score | verdict' captions."""

    st.image(
        [row["A+ Image URL"] for row in rows],
        width=width,
        caption=[
            f"#{row['A+ Image']} | "
            f"{row['Score'] if row['Score'] is not None else '-'} | {row['Verdict']}"
            for row in rows
        ]
    )


def _kind(status):
    """Badge colour for a status."""

    if status in (STATUS_DISPLAYED, VERDICT_SAME):
        return "ok"

    if status in (STATUS_NOT_DISPLAYED, VERDICT_DIFFERENT):
        return "bad"

    if status == VERDICT_NOT_CHECKED:
        return "info"

    return "warn"


def show_content_check(result, badge):
    """Draw the content display and A+ design results for one product."""

    display = result.get("content_display") or {}

    if not display:
        return

    design = result.get("design_check") or {}

    listing = display.get("listing_images") or {}
    aplus = display.get("aplus") or {}
    brand = display.get("brand_story") or {}

    st.subheader("A+ Content, Brand Story and Images")

    design_status = design.get("overall") or "Not checked"

    st.markdown(
        " ".join([
            badge(f"Images: {listing.get('count', 0)}", _kind(listing.get("status"))),
            badge(f"A+: {aplus.get('status')}", _kind(aplus.get("status"))),
            badge(f"Brand Story: {brand.get('status')}", _kind(brand.get("status"))),
            badge(f"A+ design: {design_status}", _kind(design_status)),
        ]),
        unsafe_allow_html=True
    )

    st.caption(
        f"A+ modules: {aplus.get('modules', 0)} | A+ images: {aplus.get('image_count', 0)} | "
        f"Brand Story images: {brand.get('image_count', 0)}. "
        "NOT DISPLAYED means it was not found on the live page; confirm in Seller Central."
    )

    for finding in result.get("content_findings", []):
        st.warning(f"{finding.get('Item')}: {finding.get('Detail')}")

    # Side-by-side pictures: the quickest way for a person to confirm.
    if listing.get("images"):
        with st.expander(f"Listing images ({listing.get('count', 0)})", expanded=False):
            st.image(listing["images"][:10], width=110)

    rows = design.get("rows") or []

    if rows:

        with st.expander("A+ images compared with the listing images", expanded=True):

            if listing.get("main_image"):
                st.caption("Main listing image")
                st.image(listing["main_image"], width=160)

            review = [r for r in rows if r["Verdict"] in (VERDICT_DIFFERENT, VERDICT_UNCERTAIN)]
            same = [r for r in rows if r["Verdict"] == VERDICT_SAME]
            skipped = [r for r in rows if r["Verdict"] == VERDICT_SKIPPED]
            other = [r for r in rows if r not in review + same + skipped]

            if review:
                st.markdown(
                    badge(f"{len(review)} image(s) to review", "bad"),
                    unsafe_allow_html=True
                )
                _show_images(review)

            if same:
                st.caption(f"Likely the same design ({len(same)}) - score 0 to 1")
                _show_images(same, width=130)

            if other:
                st.caption("Not compared (could not be downloaded)")
                _show_images(other, width=110)

            if skipped:
                st.caption(
                    f"Skipped: {len(skipped)} graphic, text or icon image(s). "
                    "They are not product photos, so they are not compared."
                )
                _show_images(skipped, width=90)

            st.caption(design.get("note", ""))

    elif aplus.get("images"):

        with st.expander(f"A+ images ({aplus.get('image_count', 0)})", expanded=False):
            st.image(aplus["images"][:12], width=160)

            if design.get("note"):
                st.caption(design["note"])

    if brand.get("images"):
        with st.expander(f"Brand Story images ({brand.get('image_count', 0)})", expanded=False):
            st.image(brand["images"][:12], width=140)
            st.caption("Brand Story shows the brand range, so it is not compared for design.")
