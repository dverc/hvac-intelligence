from app.services.service_area_service import extract_zip_from_address, is_address_serviceable

_SERVICE_AREA_SETTINGS = {
    "service_area": {
        "zip_codes": ["92612", "92614", "92618", "92620"],
        "radius_miles": 25,
        "center_zip": "92612",
    }
}


def test_returns_true_when_zip_is_in_configured_list():
    serviceable, message = is_address_serviceable(
        "123 Main St, Irvine, CA 92612",
        _SERVICE_AREA_SETTINGS,
    )
    assert serviceable is True
    assert message == "Address is within our service area."


def test_returns_false_when_zip_is_not_in_list():
    serviceable, message = is_address_serviceable(
        "456 Oak Ave, Los Angeles, CA 90001",
        _SERVICE_AREA_SETTINGS,
    )
    assert serviceable is False
    assert message == "Unfortunately we don't currently service that ZIP code."


def test_returns_true_when_no_service_area_config_exists():
    serviceable, message = is_address_serviceable(
        "123 Main St, Irvine, CA 92612",
        {},
    )
    assert serviceable is True
    assert message == "All areas serviceable."


def test_returns_true_when_address_has_no_zip_code():
    serviceable, message = is_address_serviceable(
        "123 Main St, Irvine, CA",
        _SERVICE_AREA_SETTINGS,
    )
    assert serviceable is True
    assert message == "Could not verify service area from address — proceeding."


def test_extracts_zip_from_full_address_string():
    assert (
        extract_zip_from_address("123 Main St, Irvine, CA 92612") == "92612"
    )
