"""Tests for user-input parsing (Airbnb links, uploaded columns).

Run: python -m pytest tests/ -v
"""

from str_audit.parse import parse_listing_id
from str_audit.upload import map_uploaded_row


def test_parse_listing_id_variants():
    assert parse_listing_id("21004527") == 21004527
    assert parse_listing_id("https://www.airbnb.com/rooms/21004527") == 21004527
    assert parse_listing_id("https://www.airbnb.com/rooms/plus/5094445?adults=2") == 5094445
    assert parse_listing_id("airbnb.com/rooms/21004527?check_in=2026-08-01&adults=2") == 21004527
    assert parse_listing_id("hello") is None
    assert parse_listing_id("") is None
    assert parse_listing_id(None) is None


def test_upload_mapping_template_csv():
    row = {"name": "My place", "price": 150, "room_type": "Entire home/apt",
           "neighbourhood": 78704, "bedrooms": 1, "beds": 1, "baths": 1,
           "availability_365": 280, "number_of_reviews": 12,
           "reviews_per_month": 0.4, "last_review": "2026-08-01",
           "description": "Cozy spot", "photo_count": 5}
    out = map_uploaded_row(row)
    t, m = out["target"], out["mapping"]
    assert t["price"] == 150.0 and t["name"] == "My place"
    assert t["neighbourhood"] == "78704"
    assert m["neighbourhood"] == "neighbourhood"
    assert out["photo_count"] == 5 and not out["missing"]


def test_upload_mapping_messy_headers():
    row = {"Nightly price": "$1,250.00", "Room Type": "Entire condo",
           "ZIP": "78704", "Bedrooms": 2, "Number of Reviews": 33,
           "Bathrooms Text": "1.5 baths", "Photos": 9}
    out = map_uploaded_row(row)
    t, m = out["target"], out["mapping"]
    assert t["price"] == 1250.0
    assert t["room_type"] == "Entire home/apt"
    assert t["baths"] == 1.5
    assert t["number_of_reviews"] == 33.0
    assert m["price"] == "nightly_price" and m["bedrooms"] == "bedrooms"
    assert out["photo_count"] == 9


def test_upload_missing_price_reported():
    out = map_uploaded_row({"title": "x", "room_type": "Private room"})
    assert out["missing"] == ["price"]
    assert out["target"]["room_type"] == "Private room"


def test_upload_defaults_for_thin_files():
    out = map_uploaded_row({"price": 99})
    t = out["target"]
    assert t["room_type"] == "Entire home/apt"
    assert t["neighbourhood"] == "78704"
    assert t["name"] == "Uploaded listing"
