from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path("scripts").resolve()))

from assembly.review_state import build_initial_review_state, validate_review_state


def test_review_state_builds_for_awdmods_fixture():
    engagement = Path("docs/ecp/2026-05-01-d5ebb62c")
    if not engagement.exists():
        pytest.skip("AWDMods fixture engagement (docs/ecp/2026-05-01-d5ebb62c) not present; restore it locally to run this review-state test")

    desktop = build_initial_review_state(engagement, "desktop", plugin_root=Path("."))
    mobile = build_initial_review_state(engagement, "mobile", plugin_root=Path("."))

    assert validate_review_state(desktop) == []
    assert validate_review_state(mobile) == []
    assert len(desktop["findings"]) == 19
    assert len(mobile["findings"]) == 22
    assert desktop["markers"][0]["marker_id"]
    assert desktop["slide_edits"][0]["crop"]["w_pct"] == 100


def test_review_state_reports_broken_marker_reference():
    engagement = Path("docs/ecp/2026-05-01-d5ebb62c")
    if not engagement.exists():
        pytest.skip("AWDMods fixture engagement (docs/ecp/2026-05-01-d5ebb62c) not present; restore it locally to run this review-state test")

    state = build_initial_review_state(engagement, "desktop", plugin_root=Path("."))
    state["findings"][0]["marker_id"] = "missing-marker"

    assert "findings[0].marker_id does not reference markers[]" in validate_review_state(state)


def test_laptop_review_state_smoke():
    engagement = Path("docs/ecp/2026-05-01-d5ebb62c")
    if not engagement.exists():
        pytest.skip("AWDMods fixture engagement (docs/ecp/2026-05-01-d5ebb62c) not present; restore it locally to run this laptop smoke test")

    state = build_initial_review_state(engagement, "laptop", plugin_root=Path("."))

    assert state["device"] == "laptop"
    assert validate_review_state(state) == []
