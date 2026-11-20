"""
Text inside images - result screen for one product (presentation only).
"""

import streamlit as st

from modules.image_text import STATUS_READ, STATUS_NOT_INSTALLED, STATUS_NO_IMAGES


def show_visual_check(result, badge):
    """Colour name vs listing images, and videos vs listing images."""

    report = result.get("visual") or {}

    if not report:
        return

    st.subheader("Colour and video check")

    colour = report.get("colour") or {}
    findings = report.get("findings") or []

    status = colour.get("status", "")

    st.markdown(
        "**Colour on the page:** " + (colour.get("colour") or "not shown") + "  "
        + badge(status or "NOT CHECKED",
                "ok" if status == "COLOUR VISIBLE" else ("warn" if "REVIEW" in status else "info")),
        unsafe_allow_html=True
    )

    if colour.get("shares"):
        st.dataframe(colour["shares"], width="stretch", hide_index=True)

    videos = report.get("videos") or []

    if videos:
        st.write(f"**Videos compared with the listing images:** {len(videos)}")
        st.dataframe(
            [{key: value for key, value in row.items() if key != "URL"} for row in videos],
            width="stretch", hide_index=True
        )
    else:
        st.caption("No videos found next to the listing images.")

    for finding in findings:
        st.warning(f"{finding['area']}: {finding['rule']}. {finding['action']}")

    st.caption("Colour and video results are hints from the image colours: check flagged ones by eye.")


def show_image_text(result, badge):
    """Draw what was read from the images and any problems found."""

    report = result.get("image_text") or {}

    if not report:
        return

    st.subheader("Text inside images")

    status = report.get("status")

    if status == STATUS_NOT_INSTALLED:
        st.warning(
            "Text reading (OCR) is not installed on this laptop. Double-click "
            "\"Install Audit Bot.bat\" once to add it."
        )
        return

    if status == STATUS_NO_IMAGES:
        st.info("No listing or A+ images were found to read.")
        return

    if status != STATUS_READ:
        st.warning("The image text could not be read: " + str(report.get("note", status)))
        return

    images = report.get("images") or []
    findings = report.get("findings") or []

    with_text = sum(1 for row in images if row.get("text"))

    st.markdown(
        " ".join([
            badge(f"{len(images)} image(s) read", "info"),
            badge(f"{with_text} with text", "info"),
            badge(f"{len(findings)} problem(s)", "bad" if findings else "ok"),
        ]),
        unsafe_allow_html=True
    )

    if findings:
        st.dataframe(
            [
                {
                    "Severity": finding.get("severity"),
                    "Image": finding.get("area"),
                    "Issue": finding.get("rule"),
                    "Image Shows": finding.get("found"),
                    "Should Be": finding.get("expected"),
                    "What To Do": finding.get("action"),
                }
                for finding in findings
            ],
            width="stretch",
            hide_index=True
        )
    else:
        st.success("No spelling or size problems found in the image text.")

    with st.expander("Show the text read from each image"):

        for row in images:

            col1, col2 = st.columns([1, 4])

            with col1:
                try:
                    st.image(row["url"], width=120)
                except Exception:
                    st.caption(row["url"])

            with col2:
                st.markdown(f"**{row['kind']} {row['number']}**")
                st.caption(row.get("text") or "(no text found)")

    st.caption(
        "Text is read on this laptop (free, offline). Reading can miss stylish "
        "fonts, so a missing word is not proof it is absent."
    )
