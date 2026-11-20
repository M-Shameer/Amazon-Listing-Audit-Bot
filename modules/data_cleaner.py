
import re
from urllib.parse import urlparse


def clean_text(text):
    """Remove unnecessary spaces and line breaks."""

    if not isinstance(text, str):
        return ""

    return re.sub(r"\s+", " ", text).strip()


def clean_technical_details(details):
    """
    Clean technical specification values.

    Removes JavaScript accidentally captured from
    Amazon's dynamically generated product page.
    """

    cleaned_details = {}

    javascript_markers = [
        r"\bvar\s+dpAcrHasRegisteredArcLinkClickAction\b",
        r"\bP\.when\s*\(",
        r"\bA\.declarative\s*\("
    ]

    for key, value in details.items():

        key = clean_text(str(key))
        value = clean_text(str(value))

        # Remove JavaScript beginning at a known marker
        for marker in javascript_markers:

            match = re.search(
                marker,
                value,
                flags=re.IGNORECASE
            )

            if match:
                value = clean_text(value[:match.start()])

        if key and value:
            cleaned_details[key] = value

    return cleaned_details


def get_image_id(image_url):
    """
    Identify the underlying Amazon image filename.

    Different resolutions of the same image have
    the same image ID.
    """

    try:

        path = urlparse(image_url).path

        match = re.search(
            r"/I/([^./]+)",
            path
        )

        if match:
            return match.group(1)

    except Exception:
        pass

    return image_url


def get_image_quality(image_url):
    """
    Estimate image resolution from Amazon's URL suffix.

    This is only a URL-based estimate, not an
    inspection of the actual image dimensions.
    """

    filename = urlparse(image_url).path

    match = re.search(
        r"_(?:SL|SX|SY|US)(\d+)_",
        filename,
        flags=re.IGNORECASE
    )

    if match:
        return int(match.group(1))

    return 0


def clean_product_images(images):
    """
    Remove duplicate image resolutions.

    Keep the highest-scoring URL for each image ID.
    Exclude known video-play-button thumbnails.
    """

    unique_images = {}

    for image_url in images:

        if not isinstance(image_url, str):
            continue

        if not image_url.startswith("https://"):
            continue

        # Ignore known video thumbnail artwork
        if "play-button" in image_url.lower():
            continue

        image_id = get_image_id(image_url)

        if image_id not in unique_images:

            unique_images[image_id] = image_url

        else:

            existing_url = unique_images[image_id]

            if get_image_quality(
                image_url
            ) > get_image_quality(existing_url):

                unique_images[image_id] = image_url

    return list(unique_images.values())


def clean_product_data(product_data):
    """
    Clean extracted Amazon product information
    before passing it to the audit engine.

    Does not change the original Amazon listing.
    """

    cleaned_data = product_data.copy()

    # Clean technical specifications
    technical_details = cleaned_data.get(
        "technical_details",
        {}
    )

    if isinstance(technical_details, dict):

        cleaned_data["technical_details"] = (
            clean_technical_details(technical_details)
        )

    # Clean and deduplicate images
    images = cleaned_data.get(
        "images",
        []
    )

    if isinstance(images, list):

        cleaned_images = clean_product_images(
            images
        )

        cleaned_data["images"] = cleaned_images

        if cleaned_images:

            cleaned_data["image_url"] = (
                cleaned_images[0]
            )

            cleaned_data["images_status"] = (
                "EXTRACTED - DEDUPLICATED"
            )

        else:

            cleaned_data["image_url"] = ""

            cleaned_data["images_status"] = (
                "NOT VERIFIED"
            )

    return cleaned_data
