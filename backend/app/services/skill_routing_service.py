"""Issue-type to technician skill mapping for dispatch routing."""

from __future__ import annotations

ISSUE_TYPE_SKILLS: dict[str, str] = {
    "AC_FAILURE": "hvac",
    "FURNACE_FAILURE": "hvac",
    "HEAT_PUMP": "hvac",
    "REFRIGERANT_LEAK": "refrigeration",
    "PLUMBING": "plumbing",
    "DRAIN_CLOG": "plumbing",
    "WATER_HEATER": "plumbing",
    "ELECTRICAL": "electrical",
    "PANEL_UPGRADE": "electrical",
    "ROOFING": "roofing",
    "RESTORATION": "restoration",
    "APPLIANCE": "appliance",
    "GARAGE_DOOR": "garage_door",
    "LOCKSMITH": "locksmith",
    "PEST_CONTROL": "pest_control",
}


def get_required_skill(issue_type: str) -> str | None:
    """Return the required technician skill for an issue type, or None if unmapped."""
    if not issue_type:
        return None
    return ISSUE_TYPE_SKILLS.get(issue_type.strip().upper())
