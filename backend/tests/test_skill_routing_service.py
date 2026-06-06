from app.services.skill_routing_service import get_required_skill


def test_get_required_skill_returns_correct_skill_for_known_issue_types():
    assert get_required_skill("AC_FAILURE") == "hvac"
    assert get_required_skill("REFRIGERANT_LEAK") == "refrigeration"
    assert get_required_skill("DRAIN_CLOG") == "plumbing"
    assert get_required_skill("PEST_CONTROL") == "pest_control"


def test_get_required_skill_returns_none_for_unknown_issue_type():
    assert get_required_skill("UNKNOWN_ISSUE") is None


def test_get_required_skill_is_case_insensitive():
    assert get_required_skill("ac_failure") == "hvac"
    assert get_required_skill("Ac_Failure") == "hvac"
    assert get_required_skill("AC_FAILURE") == "hvac"
