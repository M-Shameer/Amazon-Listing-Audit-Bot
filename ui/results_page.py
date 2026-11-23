"""
Clear batch results screen (presentation only).

Order on the page:
1. A warning when products could not be checked (e.g. Amazon was not
   using the saved postcode) - shown ONCE, not on every row.
2. Headline numbers and the Excel download.
3. Three tabs:
   - "By product":  ONE row per ASIN, everything wrong in one cell.
   - "Every issue": one row per issue, with filters.
   - "Recommendations": advice that is not a rule break.
   Each tab has a "Copy for Excel" box: click the copy icon at its top
   right, then paste into Excel - the columns stay separate.
4. Where the time went, and the full details of one product.
"""

import streamlit as st

from services.issue_report import (
    build_issue_rows,
    build_product_scorecard,
    batch_totals,
    not_checked_summary,
    rows_to_tsv,
)


SEVERITY_LABELS = {
    "High": "🔴 High",
    "Medium": "🟠 Medium",
    "Low": "🟡 Low",
    "Check": "🔵 Check",
    "Advice": "🟢 Advice",
}

PROBLEM_LEVELS = ["High", "Medium", "Low", "Check"]

PRODUCT_COLUMNS = [
    "ASIN", "Result", "Buy Box", "What's Wrong", "High", "Medium", "Low", "Check",
    "Seconds", "Title",
]

NOT_CHECKED_MESSAGES = {
    "LOCATION NOT VERIFIED": (
        "Amazon was not using your saved postcode, so {count} product(s) were "
        "NOT checked (nothing is known about them yet). Open Delivery Location, "
        "click 'Verify Location in Chrome', then run the audit again."
    ),
    "BLOCKED BY AMAZON": (
        "Amazon showed a security check for {count} product(s), so they were not "
        "checked. Turn off 'Run Chrome in the background', run them again and "
        "complete the check in the Chrome window."
    ),
    "FAILED": "{count} product page(s) could not be opened. Check those links or ASINs.",
}


def _average_timings(results):
    """Average seconds per audit step across all products."""

    totals = {}
    counts = {}

    for result in results:
        for step, seconds in (result.get("timings") or {}).items():
            totals[step] = totals.get(step, 0) + seconds
            counts[step] = counts.get(step, 0) + 1

    return [
        {"Step": step, "Average seconds": round(totals[step] / counts[step], 2)}
        for step in totals
    ]


def _copy_box(rows, columns, key):
    """A box whose copy icon copies the table for pasting into Excel."""

    if not rows:
        return

    with st.expander("📋 Copy for Excel"):
        st.caption("Click the copy icon at the top right of the box, then paste into Excel.")
        st.code(rows_to_tsv(rows, columns), language=None)


def show_batch_results(results, workbook_bytes, file_name, xlsx_mime, show_details, caption=""):
    """
    Draw the results of a finished run.

    workbook_bytes: the Excel report (bytes) for the download button.
    show_details:   function(result) that draws one product's full details.
    """

    totals = batch_totals(results)

    st.subheader("Audit Results")

    if caption:
        st.caption(caption)

    # ---------- 0. Products that could not be checked ----------

    for status, asins in not_checked_summary(results).items():
        st.error(
            NOT_CHECKED_MESSAGES[status].format(count=len(asins))
            + "  ASINs: " + ", ".join(asins)
        )

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("Products checked", totals["products"])
    with col2:
        st.metric("❌ Fix now", totals["fix_now"])
    with col3:
        st.metric("🟠 Improve", totals["improve"])
    with col4:
        st.metric("✅ No issues", totals["clean"])
    with col5:
        average = totals["average_seconds"]
        st.metric("Real seconds / product", average if average is not None else "-",
                  help="Total time of this audit divided by the number of products "
                       "(everything included: page, checks, image text).")

    if totals.get("total_seconds"):
        st.caption(
            f"⏱️ Whole audit: {totals['total_seconds']} s for {totals['products']} product(s). "
            f"Buy Box lost or missing: {totals.get('buy_box_lost', 0)}."
        )

    st.download_button(
        "⬇️ Download Excel report",
        data=workbook_bytes,
        file_name=file_name,
        mime=xlsx_mime,
        type="primary",
    )

    all_rows = build_issue_rows(results)
    problem_rows = [row for row in all_rows if row["Severity"] in PROBLEM_LEVELS]
    advice_rows = [row for row in all_rows if row["Severity"] == "Advice"]

    tab_product, tab_issues, tab_advice = st.tabs([
        "By product (one row per ASIN)",
        f"Every issue ({len(problem_rows)})",
        f"Recommendations ({len(advice_rows)})",
    ])

    # ---------- 1. One row per ASIN ----------

    with tab_product:

        scorecard = build_product_scorecard(results)

        product_rows = [{column: row.get(column, "") for column in PRODUCT_COLUMNS}
                        for row in scorecard]

        st.caption(
            "❌ Fix now = breaks an Amazon rule or loses sales · 🟠 Improve = "
            "weakens the listing · ⚠️ = could not be confirmed, look by eye. "
            "Hover over a cell to read all of it."
        )

        st.dataframe(
            product_rows,
            width="stretch",
            hide_index=True,
            column_config={
                "What's Wrong": st.column_config.TextColumn("What's Wrong", width="large"),
                "Title": st.column_config.TextColumn("Title", width="medium"),
            },
        )

        _copy_box(product_rows, PRODUCT_COLUMNS, "copy_products")

    # ---------- 2. One row per issue ----------

    with tab_issues:

        if not problem_rows:

            st.success("No issues found in any product.")

        else:

            asins = sorted({row["ASIN"] for row in problem_rows})

            filter_col1, filter_col2 = st.columns([2, 3])

            with filter_col1:
                chosen_asin = st.selectbox(
                    "Show product", ["All products"] + asins, key="issues_asin_filter"
                )

            with filter_col2:
                chosen_levels = st.multiselect(
                    "Severity", PROBLEM_LEVELS, default=PROBLEM_LEVELS,
                    format_func=lambda level: SEVERITY_LABELS[level],
                    key="issues_level_filter"
                )

            shown = [
                {**row, "Severity": SEVERITY_LABELS.get(row["Severity"], row["Severity"])}
                for row in problem_rows
                if row["Severity"] in chosen_levels
                and (chosen_asin == "All products" or row["ASIN"] == chosen_asin)
            ]

            st.caption(f"{len(shown)} issue(s) shown.")

            st.dataframe(
                shown,
                width="stretch",
                hide_index=True,
                column_config={
                    "What To Do": st.column_config.TextColumn("What To Do", width="large"),
                },
            )

            _copy_box(shown, None, "copy_issues")

    # ---------- 3. Recommendations ----------

    with tab_advice:

        if advice_rows:
            st.dataframe(advice_rows, width="stretch", hide_index=True)
            _copy_box(advice_rows, None, "copy_advice")
        else:
            st.success("No recommendations.")

    timings = _average_timings(results)

    if timings:
        with st.expander("Where the time went (average per product)"):
            st.dataframe(timings, width="stretch", hide_index=True)

    # ---------- 4. One product in full ----------

    st.subheader("Product details")

    results_by_asin = {result.get("asin"): result for result in results}

    chosen = st.selectbox(
        "Open the full details of one product",
        list(results_by_asin.keys()),
        key="details_asin"
    )

    if chosen:
        show_details(results_by_asin[chosen])
