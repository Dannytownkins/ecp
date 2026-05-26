from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path("scripts").resolve()))

from assembly.review_state import build_initial_review_state, render_final_report, validate_review_state, _image_data_url


def test_final_report_renders_from_review_state():
    engagement = Path("docs/ecp/2026-05-01-d5ebb62c")
    if not engagement.exists():
        pytest.skip("AWDMods fixture engagement (docs/ecp/2026-05-01-d5ebb62c) not present; restore it locally to run this render test")

    state = build_initial_review_state(engagement, "desktop", plugin_root=Path("."))
    state["findings"][0]["status"] = "hidden"

    html = render_final_report(state, engagement, "desktop")

    assert "<!doctype html>" in html
    assert "Human-reviewed ECP audit" in html
    assert "slide-card" in html
    assert state["findings"][0]["finding_title"] not in html


def test_final_report_round_trip_with_overrides():
    engagement = Path("docs/ecp/2026-05-01-d5ebb62c")
    if not engagement.exists():
        pytest.skip("AWDMods fixture engagement (docs/ecp/2026-05-01-d5ebb62c) not present; restore it locally to run this render test")

    state = build_initial_review_state(engagement, "desktop", plugin_root=Path("."))
    state["findings"][0]["status"] = "hidden"
    state["findings"][1]["finding_title_override"] = "Operator-approved title"
    state["findings"][1]["callout_title_override"] = "Operator callout"

    assert validate_review_state(state) == []
    html = render_final_report(state, engagement, "desktop")

    assert state["findings"][0]["finding_title"] not in html
    assert "Operator-approved title" in html
    assert "Operator callout" in html


def test_image_data_url_rejects_path_traversal():
    engagement = Path("docs/ecp/2026-05-01-d5ebb62c")
    if not engagement.exists():
        pytest.skip("AWDMods fixture engagement (docs/ecp/2026-05-01-d5ebb62c) not present; restore it locally to run this traversal test")

    assert _image_data_url(engagement / ".." / ".." / "README.md", engagement) == ""
