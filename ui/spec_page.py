"""
Website screens for specification templates.

- render_spec_templates_page(): the "Specification Templates" page
  (download blank template, upload filled template, manage saved sets)
- choose_spec_for_audit(): the selector shown on New Audit
- show_spec_check(): the results table for one audited product

Presentation only. The logic lives in services/spec_service.py and
modules/spec_checker.py.
"""

import streamlit as st

from services.spec_service import (
    build_blank_template,
    parse_template,
    save_spec_set,
    list_spec_sets,
    get_spec_set,
    delete_spec_set,
    product_types,
    rows_as_table,
    build_spec_for_audit,
)

from modules.spec_checker import (
    RESULT_MATCH,
    RESULT_CHECK,
    RESULT_MISMATCH,
    RESULT_NOT_SHOWN,
    STATUS_CHECKED,
    STATUS_ROW_EMPTY,
)


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

NO_SPEC = "No specification check"


# =========================================
# PAGE: SPECIFICATION TEMPLATES
# =========================================

def render_spec_templates_page():
    """Draw the whole Specification Templates page."""

    # ---- Step 1: download ----
    st.subheader("1. Download the blank template")

    st.caption(
        "One row per product type and size. Column names are Amazon's "
        "'Product information' labels. Leave a cell empty to skip that check."
    )

    st.download_button(
        "Download blank specification template (.xlsx)",
        data=build_blank_template(),
        file_name="specification_template.xlsx",
        mime=XLSX_MIME,
        type="primary"
    )

    # ---- Step 2: upload ----
    st.divider()
    st.subheader("2. Upload your filled template")

    uploaded = st.file_uploader(
        "Choose your filled .xlsx file",
        type=["xlsx"],
        key="spec_upload"
    )

    if uploaded is not None:

        parsed = parse_template(uploaded.getvalue())

        for message in parsed["errors"]:
            st.error(message)

        for message in parsed["warnings"]:
            st.warning(message)

        if not parsed["errors"]:

            types = product_types(parsed)

            st.success(
                f"Read {len(parsed['rows'])} row(s) for "
                f"{len(types)} product type(s): {', '.join(types)}. "
                f"{len(parsed['fields'])} field(s) can be checked."
            )

            st.dataframe(rows_as_table(parsed), width="stretch", hide_index=True)

            default_name = uploaded.name.rsplit(".", 1)[0]

            with st.form("save_spec_form"):

                set_name = st.text_input(
                    "Name for this specification set",
                    value=default_name,
                    help="Saving with an existing name replaces that set."
                )

                save_clicked = st.form_submit_button(
                    "Save specification set",
                    width="stretch"
                )

            if save_clicked:

                try:
                    save_spec_set(set_name, uploaded.name, parsed)
                    st.success(f"Saved '{set_name.strip()}'. Choose it on New Audit.")

                except ValueError as error:
                    st.error(str(error))

    # ---- Step 3: manage saved sets ----
    st.divider()
    st.subheader("3. Saved specification sets")

    sets = list_spec_sets()

    if not sets:
        st.info("No specification sets saved yet.")
        return

    st.dataframe(sets, width="stretch", hide_index=True)

    choices = {f"{item['name']} (uploaded {item['uploaded_at']})": item["set_id"] for item in sets}

    chosen_label = st.selectbox("View a saved set", list(choices.keys()), key="spec_view")

    spec_set = get_spec_set(choices[chosen_label])

    if spec_set:

        st.dataframe(rows_as_table(spec_set["data"]), width="stretch", hide_index=True)

        confirm = st.checkbox(
            "I want to delete this specification set",
            key=f"spec_delete_confirm_{spec_set['set_id']}"
        )

        if st.button("Delete this set", disabled=not confirm, key="spec_delete"):

            delete_spec_set(spec_set["set_id"])
            st.success("Deleted.")
            st.rerun()


# =========================================
# SELECTOR ON THE NEW AUDIT PAGE
# =========================================

def choose_spec_for_audit():
    """
    Show the specification selectors. Returns the spec dictionary for
    the audit, or None when no check is wanted.
    """

    sets = list_spec_sets()

    names = [NO_SPEC] + [item["name"] for item in sets]

    col1, col2 = st.columns(2)

    with col1:
        chosen_name = st.selectbox(
            "Check Product information against",
            names,
            key="audit_spec_set",
            help="Upload sets on the Specification Templates page."
        )

    if chosen_name == NO_SPEC:
        return None

    set_id = next(item["set_id"] for item in sets if item["name"] == chosen_name)

    spec_set = get_spec_set(set_id)

    types = product_types(spec_set["data"])

    with col2:
        chosen_type = st.selectbox(
            "Product type in this batch",
            types,
            key="audit_spec_type",
            help="All products in one batch are checked against this product type."
        )

    return build_spec_for_audit(spec_set, chosen_type)


# =========================================
# RESULTS FOR ONE PRODUCT
# =========================================

def show_spec_check(spec_check, badge):
    """Draw the specification results. badge is ui.theme.badge."""

    if not spec_check:
        return

    st.subheader("Specification Check")

    st.caption(
        f"Set: {spec_check.get('set_name')} | Product type: "
        f"{spec_check.get('product_type')} | Amazon size: "
        f"{spec_check.get('amazon_size') or 'Not read'} | Amazon shows: "
        f"{spec_check.get('variant_read') or 'no size, pieces or pack found'} | "
        f"Template row used: {spec_check.get('template_size') or 'none'}"
    )

    if spec_check.get("status") == STATUS_ROW_EMPTY:
        st.warning(
            f"The template row '{spec_check.get('product_type')} / "
            f"{spec_check.get('template_size')}' has no values filled in, so "
            "nothing was compared. Fill that row in Excel and upload the file again."
        )
        return

    if spec_check.get("status") != STATUS_CHECKED:
        st.warning(
            f"{spec_check.get('status')}. Nothing was compared. Amazon shows: "
            f"{spec_check.get('variant_read') or 'no size, pieces or pack'}. Add a "
            "template row whose Size names only facts Amazon shows, for example "
            "'Double', 'Double 4 Piece' or 'Double Pack of 2'."
        )
        return

    counts = spec_check.get("counts", {})

    st.markdown(
        " ".join([
            badge(f"{counts.get(RESULT_MATCH, 0)} match", "ok"),
            badge(f"{counts.get(RESULT_MISMATCH, 0)} mismatch", "bad"),
            badge(f"{counts.get(RESULT_CHECK, 0)} to check", "warn"),
            badge(f"{counts.get(RESULT_NOT_SHOWN, 0)} not shown", "info"),
        ]),
        unsafe_allow_html=True
    )

    st.dataframe(spec_check.get("rows", []), width="stretch", hide_index=True)

    st.caption(
        "MISMATCH = Amazon differs from your specification. CHECK = close, "
        "a person should look. NOT SHOWN = Amazon does not display this "
        "field (not proof it is missing in Seller Central)."
    )
