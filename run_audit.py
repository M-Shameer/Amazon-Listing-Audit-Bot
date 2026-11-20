
import json

# Import existing modules
from modules.amazon_extractor import extract_amazon_product
from modules.listing_audit import audit_listing
from modules.data_cleaner import clean_product_data


def run_complete_audit():

    print("\n======================================")
    print(" AMAZON UK PRODUCT LISTING AUDIT BOT ")
    print("======================================")

    product_url = input(
        "\nEnter Amazon UK Product URL: "
    ).strip()

    # Validate URL
    if not product_url.startswith(
        "https://www.amazon.co.uk/"
    ):

        print("\nERROR: Please enter a valid Amazon UK URL.")
        return

    try:

        # STEP 1: Extract product information
        print("\n[1/3] Extracting Amazon product information...")

        product_data = extract_amazon_product(
            product_url
        )

        if not product_data.get("title"):

            print("\nProduct title could not be extracted.")

            print(
                "Extraction status:",
                product_data.get("extraction_status")
            )

            print("Please check Amazon page accessibility.")
            return

        print("Product extraction completed.")

        # STEP 2: Clean product information
        print("\n[2/3] Cleaning extracted product data...")

        product_data = clean_product_data(
            product_data
        )

        print("Product data cleaning completed.")

        # STEP 3: Run listing audit
        print("\n[3/3] Auditing product listing...")

        audit_result = audit_listing(
            product_data
        )

        print("Listing audit completed.")

        # Combine results
        complete_report = {

            "product_information": product_data,

            "audit_report": audit_result

        }

        # Display complete report
        print("\n======================================")
        print("         COMPLETE AUDIT REPORT")
        print("======================================")

        print(
            json.dumps(
                complete_report,
                indent=4,
                ensure_ascii=False
            )
        )

        # Display summary
        summary = audit_result["summary"]

        print("\n======================================")
        print("              AUDIT SUMMARY")
        print("======================================")

        print("ASIN:", summary["asin"])

        print(
            "Confirmed Errors:",
            summary["confirmed_errors"]
        )

        print(
            "Observations:",
            summary["observations"]
        )

        print(
            "Data Gaps:",
            summary["data_gaps"]
        )

        print(
            "Final Result:",
            summary["audit_result"]
        )

        print(
            "\nUnique Product Images:",
            len(product_data.get("images", []))
        )

        print(
            "Technical Details:",
            len(product_data.get("technical_details", {}))
        )

        print("\n======================================")
        print("             AUDIT FINISHED")
        print("======================================")


    except Exception as error:

        print("\nAn error occurred during the audit.")
        print("Error details:", str(error))


if __name__ == "__main__":

    run_complete_audit()
