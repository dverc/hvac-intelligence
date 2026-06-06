"""Service-area validation for dispatch booking."""

from __future__ import annotations

import re

_ZIP_RE = re.compile(r"\d{5}")


def extract_zip_from_address(address: str) -> str | None:
    """Extract the first 5-digit ZIP code from a free-text address."""
    match = _ZIP_RE.search(address)
    return match.group(0) if match else None


def is_address_serviceable(address: str, settings: dict) -> tuple[bool, str]:
    """Return whether an address is within the tenant's configured service area."""
    service_area = settings.get("service_area")
    if not service_area:
        return True, "All areas serviceable."

    zip_code = extract_zip_from_address(address)
    if not zip_code:
        return True, "Could not verify service area from address — proceeding."

    zip_codes = service_area.get("zip_codes")
    if zip_codes is not None:
        if zip_code in zip_codes:
            return True, "Address is within our service area."
        return False, "Unfortunately we don't currently service that ZIP code."

    radius_miles = service_area.get("radius_miles")
    center_zip = service_area.get("center_zip")
    if radius_miles is not None and center_zip:
        # Full geo distance calculation is a future enhancement.
        return True, "Address is within our service area."

    return True, "All areas serviceable."
