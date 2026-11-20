"""
Amazon UK Listing Audit Bot - Streamlit website (presentation layer).

This file only builds the screens and handles button clicks.
Business logic lives in config/, services/, modules/, reports/ and database/.
"""

import re
import streamlit as st

from config.settings_manager import (
    load_settings,
    save_delivery_postcode,
    save_expected_seller,
    save_ui_theme,
    save_background_browser,
    clear_delivery_location
)

from services.batch_audit_service import (
    run_batch_audit,
    build_summary_rows,
    save_batch_report
)

from services.link_parser import parse_url_list
from modules.amazon_session import verify_location_in_window
from services.variation_service import (
    load_variation_matrix,
    base_size_options,
    variations_of_base,
    items_for_base_size,
    group_by_size,
)
from services.consistency_checker import check_consistency
from services.history_service import (
    save_run,
    get_run_list,
    get_issue_statuses,
    set_issue_status,
    get_all_issues_with_status,
    compare_with_previous,
    compare_recheck_against_run,
    trackable_issues
)

from reports.excel_generator import build_batch_workbook, build_matrix_workbook
from reports.history_excel import build_run_workbook
from ui.theme import apply_theme, render_header, badge, render_feature_grid
from ui.content_page import show_content_check
from ui.results_page import show_batch_results
from ui.image_text_page import show_image_text, show_visual_check
from ui.spec_page import (
    render_spec_templates_page,
    choose_spec_for_audit,
    show_spec_check
)
from database.support_cases import (
    CASE_STATUSES,
    get_asins_for_run,
    get_findings_for_run_asin,
    build_draft,
    create_case,
    list_cases,
    get_case,
    update_case
)
from database.db import get_connection


# =========================================
# PAGE NAMES
# =========================================

PAGE_DASHBOARD = "Dashboard"
PAGE_NEW_AUDIT = "New Audit"
PAGE_SPECS = "Specification Templates"
PAGE_VARIATIONS = "Variation Matrix"
PAGE_HISTORY = "Audit History"
PAGE_CORRECTIONS = "Correction Tracker"
PAGE_DELIVERY = "Delivery Location"
PAGE_SUPPORT = "Support Cases"

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

STATUS_OPTIONS = [
    "Not Started",
    "In Progress",
    "Corrected by Seller",
    "Waiting for Recheck",
    "Verified Fixed",
    "Still Present",
]


# =========================================
# PAGE CONFIGURATION
# =========================================

st.set_page_config(
    page_title="Amazon Listing Audit Bot",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded"
)


# =========================================
# CUSTOM WEBSITE STYLING
# =========================================

# The saved colour mode (light or dark) is applied on every page.
apply_theme(load_settings().get("ui_theme", "light"))

# =========================================
# CALLBACKS
# =========================================

def go_to_delivery_location():
    """Switch the sidebar menu to the Delivery Location page."""
    st.session_state["selected_page"] = PAGE_DELIVERY


def toggle_dark_mode():
    """Save the new colour mode when the sidebar switch is flipped."""
    save_ui_theme("dark" if st.session_state["dark_mode"] else "light")


def toggle_background_browser():
    """Save whether audits run in an invisible Chrome."""
    save_background_browser(st.session_state["background_browser"])


# =========================================
# LOAD SAVED SETTINGS
# =========================================

settings = load_settings()
saved_postcode = settings.get("delivery_postcode", "")
location_confirmed = settings.get("amazon_location_confirmed", False)
expected_seller = settings.get("expected_seller", "")

# Badge colour for each short Featured Offer verdict.
VERDICT_BADGE = {
    "HELD BY YOUR SELLER": "ok",
    "HELD": "info",
    "HELD BY ANOTHER SELLER": "bad",
    "NO FEATURED OFFER": "bad",
    "BLOCKED": "warn",
    "NOT VERIFIED": "warn",
}


# =========================================
# SIDEBAR NAVIGATION
# =========================================

with st.sidebar:

    st.title("🛒 Amazon Audit")
    st.caption("Amazon UK Product Listing Auditor")

    # At the top, so it is always reachable without scrolling.
    st.toggle(
        "🌙 Dark mode",
        value=settings.get("ui_theme", "light") == "dark",
        key="dark_mode",
        on_change=toggle_dark_mode,
        help="Saved permanently. Switch back at any time."
    )

    st.divider()

    selected_page = st.radio(
        "MAIN MENU",
        [
            PAGE_DASHBOARD,
            PAGE_NEW_AUDIT,
            PAGE_SPECS,
            PAGE_VARIATIONS,
            PAGE_HISTORY,
            PAGE_CORRECTIONS,
            PAGE_DELIVERY,
            PAGE_SUPPORT
        ],
        label_visibility="visible",
        key="selected_page"
    )

    st.divider()
    st.markdown("**DELIVERY LOCATION**")

    if saved_postcode:
        st.write("📍", saved_postcode)
        if location_confirmed:
            last = str(settings.get("last_location_verified") or "")[:16].replace("T", " ")
            st.caption(
                f"Last confirmed by Amazon: {last or 'earlier'}. "
                "Checked again on every product; set automatically if Amazon forgets it."
            )
        else:
            st.warning("Not confirmed yet: use Delivery Location → Verify Location in Chrome")
    else:
        st.warning("No postcode saved")

    if expected_seller:
        st.write("🏷️ Your seller:", expected_seller)
    else:
        st.caption("Your seller name is not set (Delivery Location page).")

    st.caption("Development Version 0.18 · Local Application")


# =========================================
# SHARED HELPERS
# =========================================

def show_audit_result(result):
    """Draw the full details of one product."""

    buy_box = result.get("buy_box") or {}
    content = result.get("content") or {}
    spelling = result.get("spelling") or {}
    summary = spelling.get("summary") or {}
    issues = spelling.get("issues") or []
    data_gaps = spelling.get("data_gaps") or []

    st.subheader("Audit Summary")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Overall Status", result.get("overall_status", "Unknown"))
    with col2:
        st.metric("Confirmed Errors", summary.get("confirmed_errors", 0))
    with col3:
        st.metric("Price (UK)", buy_box.get("price") or "Not verified")

    timings = result.get("timings") or {}

    if timings:
        st.caption(
            f"Checked in {result.get('seconds', '?')} s  ·  "
            + "  ·  ".join(f"{step}: {seconds} s" for step, seconds in timings.items())
        )

    for message in result.get("errors", []):
        st.error(message)

    st.subheader("Buy Box and Delivery")

    location = buy_box.get("location") or {}

    if location.get("verified"):
        st.success(
            "Amazon is using your saved postcode: "
            + str(location.get("amazon_header", "")).strip()
        )
    else:
        st.error("Amazon location is NOT verified. Prices and delivery may be wrong.")

    verdict = buy_box.get("featured_offer_verdict") or "NOT VERIFIED"

    st.markdown(
        "**Featured Offer:** " + badge(verdict, VERDICT_BADGE.get(verdict, "warn")),
        unsafe_allow_html=True
    )

    st.caption(buy_box.get("featured_offer_status", "NOT VERIFIED"))

    dispatch_label = buy_box.get("dispatch_wording") or "Dispatches from"

    col1, col2 = st.columns(2)
    with col1:
        st.write("**Seller:**", buy_box.get("seller") or "Not verified")
        st.write(f"**{dispatch_label}:**", buy_box.get("dispatches_from") or "Not verified")
        st.write("**Availability:**", buy_box.get("availability") or "Not verified")
    with col2:
        st.write("**Add to Basket visible:**", "Yes" if buy_box.get("add_to_basket_visible") else "No")
        st.write("**Buy Now visible:**", "Yes" if buy_box.get("buy_now_visible") else "No")
        st.write("**Delivery:**", buy_box.get("delivery_text") or "Not verified")

    if buy_box.get("other_offers_text"):
        st.write("**Other offers:**", buy_box.get("other_offers_text"))

    st.write("**Buy Box status:**", buy_box.get("buy_box_status", "NOT VERIFIED"))

    st.subheader("Listing Content")

    if content.get("title"):
        st.write("**Title:**", content.get("title"))

    if content.get("bullets"):
        st.write("**Bullet points:**")
        for bullet in content.get("bullets", []):
            st.write("- " + bullet)

    st.subheader("Spelling and Rule Issues")

    if issues:

        st.dataframe(
            [
                {
                    "Issue ID": issue.get("issue_id"),
                    "Location": issue.get("location"),
                    "Found": issue.get("detected_term"),
                    "Suggested": issue.get("correct_term"),
                    "Classification": issue.get("classification"),
                    "Reason": issue.get("reason")
                }
                for issue in issues
            ],
            width="stretch"
        )

        st.caption("These are project rules (British English), not Amazon policy violations.")

    else:
        st.success("No rule-based issues found.")

    for gap in data_gaps:
        st.info(f"Not verified: {gap.get('field')}. {gap.get('reason')}")

    st.subheader("Listing Quality")

    quality = result.get("quality") or []

    if quality:

        st.dataframe(
            [
                {
                    "Severity": finding.get("severity"),
                    "Area": finding.get("area"),
                    "Issue": finding.get("rule"),
                    "Amazon Shows": finding.get("found"),
                    "Should Be": finding.get("expected"),
                    "What To Do": finding.get("action"),
                }
                for finding in quality
            ],
            width="stretch",
            hide_index=True
        )

        st.caption("Based on Amazon's title and bullet point rules. Advice rows are recommendations.")

    else:
        st.success("Title, bullet points, description and images pass the quality rules.")

    show_spec_check(result.get("spec_check"), badge)

    show_content_check(result, badge)

    show_visual_check(result, badge)

    show_image_text(result, badge)

    with st.expander("Show full raw audit data"):
        st.json(result)


def save_and_show_batch(results, rows, run_type, size_filter=""):
    """Save a finished run to the database and to session memory."""

    run_id = save_run(run_type, size_filter, results, rows)

    st.session_state["last_run_id"] = run_id
    st.session_state["batch_results"] = results
    st.session_state["batch_rows"] = rows
    st.session_state["batch_report_path"] = str(
        save_batch_report(results, rows)
    )

    return run_id


# =========================================
# DASHBOARD
# =========================================

if selected_page == PAGE_DASHBOARD:

    render_header(
        "Amazon UK Listing Audit Dashboard",
        "Monitor product listing accuracy, variation information and Featured Offers."
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Marketplace", "Amazon UK")
    with col2:
        st.metric("Default Postcode", saved_postcode or "Not set")
    with col3:
        st.metric("Location Verification", "Confirmed" if location_confirmed else "Pending")
    with col4:
        st.metric("Your Seller", expected_seller or "Not set")

    st.divider()
    st.subheader("Application Modules")

    render_feature_grid([
        ("Amazon Product Extraction", "Title, bullets, description and Product information.", "Live", "ok"),
        ("Buy Box Audit", "Featured Offer holder for your postcode, compared with your seller name.", "Live", "ok"),
        ("Listing Audit Engine", "British English rules such as Microfiber to Microfibre.", "Live", "ok"),
        ("Specification Check", "Your Excel specification compared with Amazon's Product information.", "Live", "ok"),
        ("Batch Audit", "Paste many links or ASINs from Excel and audit them together.", "Live", "ok"),
        ("Variation Matrix", "Reads every colour and size; audits one size across all colours.", "Live", "ok"),
        ("Consistency Check", "Compares colours of one size; gaps shown as Not verified.", "Live", "ok"),
        ("Audit History", "Every run saved permanently in SQLite.", "Live", "ok"),
        ("Correction Tracker", "Keep the correction status of every finding.", "Live", "ok"),
        ("Recheck", "Re-audit saved products: fixed or still present.", "Live", "ok"),
        ("Excel Reports", "Batch, matrix, history and specification downloads.", "Live", "ok"),
        ("A+ / Brand Story / Images", "Checks A+ content, Brand Story and images are displayed; A+ design compared with listing images.", "Live", "ok"),
        ("Text Inside Images (OCR)", "Free, offline: spelling, size, pieces and pack written on images.", "Live", "ok"),
        ("AI Audit Engine", "Optional paid add-on for later; the bot works fully without it.", "Optional", "warn"),
    ])

    st.divider()
    st.subheader("Getting Started")

    if not saved_postcode:
        st.warning("First, open Delivery Location and save your default Amazon UK postcode.")
        st.button("Open Delivery Location", on_click=go_to_delivery_location)
    elif not location_confirmed:
        st.info(
            "Your postcode is saved. It must still be verified in the Amazon "
            "browser before delivery and Buy Box results can be trusted."
        )
    else:
        st.success("Your default postcode is saved and verified. You can now run an audit.")


# =========================================
# NEW AUDIT (paste one or many links)
# =========================================

elif selected_page == PAGE_NEW_AUDIT:

    render_header(
        "New Product Audit",
        "Paste one or more Amazon UK links or ASINs, straight from Excel or one per line. Each product is audited separately."
    )

    if saved_postcode:
        st.info(f"Default delivery postcode: {saved_postcode}")
    else:
        st.warning("You must save a delivery postcode before preparing an audit.")

    # Chosen outside the form so the product type list updates at once.
    chosen_spec = choose_spec_for_audit()

    st.toggle(
        "Run Chrome in the background (no windows)",
        value=settings.get("background_browser", True),
        key="background_browser",
        on_change=toggle_background_browser,
        help="On: Chrome works invisibly and nothing pops up. "
             "Off: you can watch Chrome open each product."
    )

    with st.form("new_audit_form"):

        links_text = st.text_area(
            "Amazon UK product links or ASINs",
            height=220,
            placeholder=(
                "https://www.amazon.co.uk/dp/B0AAAAAA01\n"
                "B0AAAAAA02\n"
                "(Or paste a whole Excel column here)"
            ),
            help="Up to 50 products per run. Headers and other text are ignored. Duplicates are skipped."
        )

        audit_type = st.selectbox(
            "Select Audit Type",
            ["Full Listing Audit", "Recheck Previously Identified Issues", "Variation Comparison"]
        )

        st.checkbox("Mandatory Buy Box / Featured Offer check", value=True, disabled=True)

        check_design = st.checkbox(
            "Check design and colour: A+ images, videos and the colour name "
            "match the listing images",
            value=True,
            help="Downloads the images and compares their colours. "
                 "Adds a few seconds per product."
        )

        check_text = st.checkbox(
            "Read the text inside the images (spelling, size, pieces, pack)",
            value=True,
            help="Free and offline. About 1 second per image, done in the "
                 "background while the next product loads."
        )

        submitted = st.form_submit_button(
            "Run Audit",
            disabled=not bool(saved_postcode),
            width="stretch"
        )

    if submitted:

        valid_items, rejected = parse_url_list(links_text)

        if rejected:
            with st.expander(f"{len(rejected)} line(s) skipped", expanded=True):
                st.dataframe(rejected, width="stretch")

        if not valid_items:
            st.error("No valid Amazon UK product links or ASINs found.")

        else:

            if load_settings().get("background_browser", True):
                st.info(
                    f"Auditing {len(valid_items)} product(s) in the background. "
                    "No Chrome window will open; you can keep working."
                )
            else:
                st.info(
                    f"Auditing {len(valid_items)} product(s). One Chrome window opens "
                    "and checks each product in turn. Do not close it."
                )

            progress_bar = st.progress(0.0, text="Starting...")

            def on_progress(index, total, asin):
                progress_bar.progress(
                    index / total,
                    text=f"Auditing {asin} ({index + 1} of {total})..."
                )

            results = run_batch_audit(
                valid_items, audit_type, on_progress, chosen_spec, check_design, check_text
            )

            progress_bar.progress(1.0, text="Finished")

            rows = build_summary_rows(results)

            save_and_show_batch(results, rows, "New Audit")

    if st.session_state.get("batch_rows"):

        st.divider()

        show_batch_results(
            st.session_state["batch_results"],
            build_batch_workbook(
                st.session_state["batch_rows"],
                st.session_state["batch_results"]
            ),
            "batch_audit.xlsx",
            XLSX_MIME,
            show_audit_result,
            caption=(
                "Saved to history (run " + str(st.session_state.get("last_run_id", ""))
                + "). Full report: " + st.session_state.get("batch_report_path", "")
            ),
        )


# =========================================
# SPECIFICATION TEMPLATES (download, upload, manage)
# =========================================

elif selected_page == PAGE_SPECS:

    render_header(
        "Specification Templates",
        "Download the Excel template, fill in your verified product data, upload it, then choose it on New Audit."
    )

    render_spec_templates_page()


# =========================================
# VARIATION MATRIX (one size, all colours)
# =========================================

elif selected_page == PAGE_VARIATIONS:

    render_header(
        "Variation Matrix",
        "Reads every colour and size from one product page, then audits all colours of the size you choose."
    )

    if not saved_postcode:
        st.warning("Save a delivery postcode first.")

    with st.form("variation_form"):

        parent_url = st.text_input(
            "Product link (any ASIN from the same product family)",
            placeholder="https://www.amazon.co.uk/dp/B0AAAAAA01"
        )

        load_clicked = st.form_submit_button(
            "Load Colour and Size Matrix",
            disabled=not bool(saved_postcode),
            width="stretch"
        )

    if load_clicked:

        if not parent_url.startswith("https://www.amazon.co.uk/"):
            st.error("Please provide a valid Amazon UK product link.")

        else:

            with st.spinner("Opening Amazon UK and reading the variation map..."):

                try:
                    st.session_state["variation_matrix"] = load_variation_matrix(parent_url.strip())
                    st.session_state.pop("variation_results", None)

                except Exception as error:
                    st.session_state["variation_matrix"] = None
                    st.error("The matrix could not be loaded: " + str(error))

    matrix = st.session_state.get("variation_matrix")

    if matrix:

        st.write("**Map status:**", matrix.get("status"))

        if matrix.get("status") == "LOCATION NOT VERIFIED":
            st.error("Amazon is not using your saved postcode. Nothing was read.")

        rows = matrix.get("rows", [])

        if rows:

            st.success(f"Found {len(rows)} colour and size combinations.")
            st.dataframe(rows, width="stretch")

            st.download_button(
                "Download matrix as Excel",
                data=build_matrix_workbook(rows),
                file_name="variation_matrix.xlsx",
                mime=XLSX_MIME
            )

            # Sizes are grouped: "King" covers every King pack / piece
            # variation (Pack of 2, Pack of 4, 3 Piece ...) in every colour.
            options = base_size_options(rows)

            labels = {f"{base}  ({count} products)": base for base, count in options}

            chosen_label = st.selectbox(
                "Choose a size to audit (all its packs, piece counts and colours)",
                list(labels.keys()),
                key="matrix_base_size"
            )

            chosen_base = labels[chosen_label]

            variations = variations_of_base(rows, chosen_base)

            chosen_variations = st.multiselect(
                f"Variations of {chosen_base} to include",
                variations,
                default=variations,
                key=f"matrix_variations_{chosen_base}",
                help="Each pack / piece variation is a separate product with its own "
                     "details, so each is checked against its own template row."
            )

            size_items = items_for_base_size(rows, chosen_base, chosen_variations)

            colours = len({item["colour"] for item in size_items})

            st.info(
                f"{len(size_items)} product(s) will be audited: "
                f"{len(chosen_variations)} variation(s) of {chosen_base} in {colours} colour(s)."
            )

            matrix_spec = choose_spec_for_audit()

            matrix_design = st.checkbox(
                "Check design and colour: A+ images, videos and the colour name "
                "match the listing images",
                value=True,
                key="matrix_design"
            )

            matrix_text = st.checkbox(
                "Read the text inside the images (spelling, size, pieces, pack)",
                value=True,
                key="matrix_text"
            )

            if st.button(
                f"Audit all {chosen_base} products",
                width="stretch",
                disabled=not size_items
            ):

                progress_bar = st.progress(0.0, text="Starting...")

                def on_matrix_progress(index, total, asin):
                    progress_bar.progress(
                        index / total,
                        text=f"Auditing {asin} ({index + 1} of {total})..."
                    )

                results = run_batch_audit(
                    size_items, "Full Listing Audit", on_matrix_progress,
                    matrix_spec, matrix_design, matrix_text
                )

                progress_bar.progress(1.0, text="Finished")

                summary_rows = build_summary_rows(results)

                run_id = save_run("Variation Matrix", chosen_base, results, summary_rows)

                st.session_state["variation_results"] = {
                    "size": chosen_base,
                    "rows": summary_rows,
                    "results": results,
                    "items": size_items,
                    "run_id": run_id
                }

        else:
            st.warning("No colour and size map was found on this page. Send me the map status line above.")

    variation_results = st.session_state.get("variation_results")

    if variation_results:

        st.divider()

        show_batch_results(
            variation_results["results"],
            build_batch_workbook(variation_results["rows"], variation_results["results"]),
            f"variation_{variation_results['size'].replace(' ', '_')}_audit.xlsx",
            XLSX_MIME,
            show_audit_result,
            caption=(
                f"Size: {variation_results['size']} (all packs, piece counts and colours). "
                f"Saved to history (run {variation_results['run_id']})."
            ),
        )

        st.subheader("Cross-colour consistency")

        st.caption(
            "Colours are compared only with the SAME variation (same pack / piece "
            "count), because a Pack of 2 and a Pack of 4 are meant to differ."
        )

        groups = group_by_size(variation_results["results"], variation_results.get("items") or [])

        all_findings = []

        for size, group in groups.items():

            if len(group) < 2:
                continue

            for finding in check_consistency(group):
                all_findings.append({"Variation": size, **finding})

        if all_findings:
            st.dataframe(all_findings, width="stretch", hide_index=True)
            st.caption(
                "Potential discrepancies and inconsistencies are for checking, "
                "not proof of an Amazon policy problem. Colour is not compared."
            )
        else:
            st.success("No inconsistencies found between the colours of each variation.")


# =========================================
# AUDIT HISTORY (saved runs, reopen, recheck)
# =========================================

elif selected_page == PAGE_HISTORY:

    render_header(
        "Audit History",
        "Every saved run. Open one to see its products, download it as Excel, or recheck its products to see which issues are fixed."
    )

    runs = get_run_list()

    if not runs:

        st.info("No audits have been saved yet. Run an audit first.")

    else:

        st.dataframe(runs, width="stretch")

        run_ids = [run["run_id"] for run in runs]

        chosen_run_id = st.selectbox("Choose a run", run_ids)

        # Builds the workbook for the chosen run. Downloads never change data.
        st.download_button(
            "Download this run as Excel",
            data=build_run_workbook(chosen_run_id),
            file_name=f"audit_run_{chosen_run_id}.xlsx",
            mime=XLSX_MIME
        )

        st.info(
            "Recheck re-audits every product in this run from the live page and "
            "compares it with this run. Fixed issues are marked Verified Fixed in "
            "the Correction Tracker automatically. To recheck specification "
            "mismatches, choose the same specification set again below."
        )

        recheck_spec = choose_spec_for_audit()

        recheck_design = st.checkbox(
            "Also recheck the A+ design match",
            value=True,
            key="recheck_design"
        )

        recheck_text = st.checkbox(
            "Also recheck the text inside the images",
            value=True,
            key="recheck_text"
        )

        if st.button("Recheck this run", width="stretch"):

            connection = get_connection()

            try:
                saved = connection.execute(
                    "SELECT asin FROM audit_products WHERE run_id = ?",
                    (chosen_run_id,)
                ).fetchall()
            finally:
                connection.close()

            items = [
                {"url": "https://www.amazon.co.uk/dp/" + row["asin"], "asin": row["asin"]}
                for row in saved
            ]

            if not items:

                st.warning("This run has no products to recheck.")

            else:

                progress_bar = st.progress(0.0, text="Starting recheck...")

                def on_recheck_progress(index, total, asin):
                    progress_bar.progress(
                        index / total,
                        text=f"Rechecking {asin} ({index + 1} of {total})..."
                    )

                recheck_results = run_batch_audit(
                    items,
                    "Recheck Previously Identified Issues",
                    on_recheck_progress,
                    recheck_spec,
                    recheck_design,
                    recheck_text
                )

                checks_run = set()

                if recheck_text:
                    checks_run.add("ocr")

                if recheck_spec:
                    checks_run.add("spec")

                if recheck_design:
                    checks_run.add("design")

                progress_bar.progress(1.0, text="Recheck finished")

                recheck_rows = build_summary_rows(recheck_results)

                new_run_id = save_run(
                    "Recheck",
                    f"from run {chosen_run_id}",
                    recheck_results,
                    recheck_rows
                )

                comparison = []

                for result in recheck_results:

                    asin = result.get("asin", "")

                    location_ok = bool(
                        ((result.get("buy_box") or {}).get("location") or {}).get("verified")
                    )

                    comparison.extend(
                        compare_recheck_against_run(
                            chosen_run_id, asin, trackable_issues(result),
                            location_ok, checks_run
                        )
                    )

                st.session_state["recheck_comparison"] = comparison
                st.session_state["recheck_run_id"] = new_run_id

                st.success(f"Recheck saved as run {new_run_id}.")

        comparison = st.session_state.get("recheck_comparison")

        if comparison:

            st.subheader("Recheck Result")

            fixed = sum(1 for row in comparison if row["Recheck Result"] == "VERIFIED FIXED")
            still = sum(1 for row in comparison if row["Recheck Result"] == "STILL PRESENT")
            new = sum(1 for row in comparison if row["Recheck Result"] == "NEW")

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("✅ Verified fixed", fixed)
            with col2:
                st.metric("❌ Still present", still)
            with col3:
                st.metric("🆕 New", new)

            st.dataframe(comparison, width="stretch", hide_index=True)

            st.caption(
                "VERIFIED FIXED means the product was read successfully and the issue "
                "is no longer found. A failed read is never marked as fixed. NOT "
                "CHECKED THIS TIME means that check (specification, A+ design or "
                "image text) was not run in this recheck."
            )

        st.divider()

        st.subheader("Products in the selected run")

        connection = get_connection()

        try:
            products = connection.execute(
                """
                SELECT asin, colour, size, overall_status, price, seller,
                       location_verified, checked_at
                FROM audit_products
                WHERE run_id = ?
                ORDER BY product_id
                """,
                (chosen_run_id,)
            ).fetchall()
        finally:
            connection.close()

        st.dataframe([dict(row) for row in products], width="stretch")


# =========================================

# =========================================
# CORRECTION TRACKER (status per finding)
# =========================================

elif selected_page == PAGE_CORRECTIONS:

    render_header(
        "Correction Tracker",
        "Every saved finding with its correction status. Changing a status is kept permanently, across all future runs."
    )

    issues = get_all_issues_with_status()

    if not issues:
        st.info("No findings saved yet. Run an audit first.")

    else:

        statuses = [issue["status"] or "Not Started" for issue in issues]

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Findings", len(issues))
        with col2:
            st.metric("Not started", statuses.count("Not Started"))
        with col3:
            st.metric("❌ Still present", statuses.count("Still Present"))
        with col4:
            st.metric("✅ Verified fixed", statuses.count("Verified Fixed"))

        filter_col1, filter_col2 = st.columns(2)

        with filter_col1:
            asin_filter = st.selectbox(
                "Show product",
                ["All products"] + sorted({issue["asin"] for issue in issues}),
                key="tracker_asin"
            )

        with filter_col2:
            status_filter = st.multiselect(
                "Status", STATUS_OPTIONS,
                default=[status for status in STATUS_OPTIONS if status != "Verified Fixed"],
                key="tracker_status"
            )

        st.dataframe(
            [
                {
                    "ASIN": issue["asin"],
                    "Status": issue["status"] or "Not Started",
                    "Problem": issue["category"],
                    "Where": issue["location"],
                    "Amazon Shows": issue.get("original_text") or "",
                    "Should Be": issue["suggested_text"],
                    "What To Do": issue["detail"],
                    "Note": issue.get("note") or "",
                }
                for issue in issues
                if (asin_filter == "All products" or issue["asin"] == asin_filter)
                and (issue["status"] or "Not Started") in status_filter
            ],
            width="stretch",
            hide_index=True
        )

        st.subheader("Update a status")

        labels = {
            f"{issue['asin']} | {issue['location']} | {issue['fingerprint'][:8]}": issue
            for issue in issues
        }

        chosen_label = st.selectbox("Finding", list(labels.keys()))

        chosen = labels[chosen_label]

        new_status = st.selectbox(
            "New status",
            STATUS_OPTIONS,
            index=STATUS_OPTIONS.index(chosen["status"])
            if chosen["status"] in STATUS_OPTIONS else 0
        )

        note = st.text_input("Note (optional)", value=chosen.get("note") or "")

        if st.button("Save status", width="stretch"):

            set_issue_status(chosen["fingerprint"], chosen["asin"], new_status, note)

            st.success("Status saved.")
            st.rerun()


# =========================================
# DELIVERY LOCATION SETTINGS
# =========================================

elif selected_page == PAGE_DELIVERY:

    render_header(
        "Delivery Location Settings",
        "Set the default delivery destination used for all Amazon UK product audits."
    )

    st.info("Your saved postcode remains the default until you change it.")

    settings = load_settings()
    current_postcode = settings.get("delivery_postcode", "")

    with st.form("delivery_location_form"):

        st.text_input("Amazon Marketplace", value="Amazon UK", disabled=True)
        st.text_input("Delivery Country", value="United Kingdom", disabled=True)

        postcode_input = st.text_input(
            "Default UK Delivery Postcode",
            value=current_postcode,
            placeholder="Example: SW1A 1AA",
            help="Enter the UK postcode Amazon should use for delivery and Buy Box checks."
        )

        save_button = st.form_submit_button("Save Default Location", width="stretch")

    if save_button:

        try:
            updated_settings = save_delivery_postcode(postcode_input)
            st.success("Default delivery postcode saved successfully.")
            st.write("Saved postcode:", updated_settings["delivery_postcode"])
            st.rerun()

        except ValueError as error:
            st.error(str(error))

    st.divider()
    st.subheader("Current Location Status")

    settings = load_settings()
    postcode = settings.get("delivery_postcode", "")

    if postcode:

        st.write("**Saved postcode:**", postcode)

        if settings.get("amazon_location_confirmed"):
            st.success("Amazon location was previously confirmed.")
            st.write("**Last verified:**", settings.get("last_location_verified") or "Unknown")
        else:
            st.warning("Application postcode is saved, but Amazon location verification is pending.")

        if st.button("Remove Saved Postcode", type="secondary"):
            clear_delivery_location()
            st.success("Saved postcode removed.")
            st.rerun()

    else:
        st.warning("No delivery postcode has been saved yet.")

    # ---- Verify the location in a visible Chrome window ----

    if postcode:

        st.divider()
        st.subheader("Verify Location in Chrome")

        st.caption(
            "Opens ONE visible Chrome window on Amazon UK. If Amazon does not "
            "show your postcode, click the delivery location at the top of "
            "that window, enter " + postcode + " and click Apply. The window "
            "closes by itself once Amazon shows the postcode (up to 3 minutes). "
            "Background audits then use the same saved location."
        )

        if st.button("Verify Location in Chrome", type="primary"):

            with st.spinner("Waiting for Amazon to show " + postcode + " in the Chrome window..."):
                try:
                    outcome = verify_location_in_window()
                except Exception as error:
                    outcome = {"verified": False, "message": "Chrome could not start: " + str(error)}

            if outcome["verified"]:
                st.success(outcome["message"] + " You can now run audits in the background.")
            else:
                st.error(outcome["message"])

    # ---- Your seller name (for the Featured Offer ownership check) ----

    st.divider()
    st.subheader("Your Seller Name")

    st.caption(
        "Type your seller name exactly as Amazon shows it after \"Sold by\" "
        "(for example: Northwind). Each audit then tells you whether YOUR "
        "offer holds the Featured Offer. Leave it empty to only record "
        "who holds it."
    )

    with st.form("seller_name_form"):

        seller_input = st.text_input(
            "Seller name",
            value=settings.get("expected_seller", ""),
            placeholder="Example: Northwind"
        )

        seller_saved = st.form_submit_button("Save Seller Name", width="stretch")

    if seller_saved:

        try:
            save_expected_seller(seller_input)
            st.success("Seller name saved.")
            st.rerun()

        except ValueError as error:
            st.error(str(error))

    st.divider()
    st.subheader("Amazon Browser Profile")
    st.code(settings.get("browser_profile", "data/amazon_uk_profile"))
    st.caption(
        "This profile keeps the Amazon session and location. "
        "Do not share it, because it may contain session cookies."
    )


# =========================================
# SUPPORT CASES (placeholder for later phase)
# =========================================

elif selected_page == PAGE_SUPPORT:

    render_header(
        "Seller Support Case Assistant",
        "Prepare case notes from saved findings, then track them here. Nothing is sent to Amazon automatically."
    )

    st.warning(
        "This page never submits a case. Copy the draft into Seller Central "
        "yourself, then record the Amazon case ID and status below."
    )

    # ---- 1. Create a draft from a saved run ----

    st.subheader("1. Create a case draft")

    runs = get_run_list()

    if not runs:

        st.info("No saved runs yet. Run an audit first.")

    else:

        chosen_run = st.selectbox(
            "Saved run",
            [run["run_id"] for run in runs],
            key="case_run"
        )

        asins = get_asins_for_run(chosen_run)

        chosen_asin = st.selectbox("Product", asins, key="case_asin")

        findings = get_findings_for_run_asin(chosen_run, chosen_asin)

        if not findings:

            st.success(
                "No findings were saved for this product in this run, "
                "so there is nothing to report."
            )

        else:

            st.write(f"**{len(findings)} finding(s)** for this product.")

            draft = st.text_area(
                "Draft (you can edit it before saving)",
                value=build_draft(chosen_asin, findings),
                height=260,
                key="case_draft"
            )

            case_title = st.text_input(
                "Short title for this case",
                value=f"Listing wording review - {chosen_asin}",
                key="case_title"
            )

            if st.button("Save case draft", width="stretch"):

                if not case_title.strip() or not draft.strip():

                    st.error("A title and draft text are required.")

                else:

                    new_case_id = create_case(
                        chosen_asin,
                        chosen_run,
                        case_title.strip(),
                        draft.strip()
                    )

                    st.success(f"Case {new_case_id} saved as a draft.")

    # ---- 2. Track all cases ----

    st.divider()

    st.subheader("2. Track your cases")

    cases = list_cases()

    if not cases:

        st.info("No cases yet. Create a draft above.")

    else:

        st.dataframe(
            [
                {
                    "Case": case["case_id"],
                    "ASIN": case["asin"],
                    "Title": case["title"],
                    "Status": case["status"],
                    "Amazon Case ID": case["amazon_case_id"],
                    "Updated": case["updated_at"],
                }
                for case in cases
            ],
            width="stretch"
        )

        case_choices = {
            f"Case {case['case_id']} | {case['asin']} | {case['title']}": case["case_id"]
            for case in cases
        }

        chosen_label = st.selectbox(
            "Choose a case to update",
            list(case_choices.keys()),
            key="case_choice"
        )

        case = get_case(case_choices[chosen_label])

        with st.expander("Show the draft text (copy from here)", expanded=True):

            st.text_area(
                "Draft",
                value=case["draft_text"],
                height=240,
                key=f"case_view_{case['case_id']}"
            )

            st.download_button(
                "Download draft as a text file",
                data=case["draft_text"],
                file_name=f"case_{case['case_id']}_{case['asin']}.txt",
                mime="text/plain"
            )

        status_index = (
            CASE_STATUSES.index(case["status"])
            if case["status"] in CASE_STATUSES else 0
        )

        new_status = st.selectbox(
            "Status",
            CASE_STATUSES,
            index=status_index,
            key=f"case_status_{case['case_id']}"
        )

        amazon_id = st.text_input(
            "Amazon case ID (type it in after you submit in Seller Central)",
            value=case["amazon_case_id"],
            key=f"case_amazon_{case['case_id']}"
        )

        case_notes = st.text_area(
            "Notes (replies, dates, what Amazon asked for)",
            value=case["notes"],
            height=120,
            key=f"case_notes_{case['case_id']}"
        )

        if st.button("Save case update", width="stretch"):

            update_case(case["case_id"], new_status, amazon_id, case_notes)

            st.success("Case updated.")

            st.rerun()

# =========================================
# FOOTER
# =========================================

st.divider()

st.caption(
    "Amazon UK Product Listing Audit Bot | Local Development Application | "
    "Python + Streamlit + Playwright"
)