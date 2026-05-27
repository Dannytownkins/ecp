"""G4 (product.md §4.2) — below the auto-place confidence threshold, the
hotspot is left BLANK for manual placement instead of auto-placing a guess.

Before 2026-05-26 the last-resort "banner" strategy pinned an unplaceable
finding at a top-of-page indicator (an auto-placed guess). The spec is
explicit: "a wrong hotspot costs more than a missing one; a blank is neutral.
Below threshold -> leave it blank. Never auto-place a guess." This regression
locks in the blank-and-queue behavior:

- auto_map_markers_v2 emits match_method="unplaced" with fallback_position=None
  (no position) for a finding with no usable placement signal.
- compute_marker_positions_v2 renders NO marker for it (truly blank).
- review_state surfaces it in the editor's "Place manually" queue
  (hotspot_confidence="needs-manual-marker") with a hidden, coord-less marker
  that the final-report renderer draws as nothing.
- The Phase-3 visual-evidence footprint stays page_level/low (same as the old
  banner), so this fix doesn't silently change the priority-path gate.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts"))

from report.v2_markers import auto_map_markers_v2, compute_marker_positions_v2  # noqa: E402
from report.visual_evidence import derive_visual_evidence  # noqa: E402
from assembly.review_state import (  # noqa: E402
    _hotspot_confidence,
    _marker_from_ai,
    _render_marker_svg,
    _unplaced_marker,
)


def _baton():
    """One real element on slide 0; a second slide so geometry is non-trivial."""
    return {
        "device": "laptop",
        "viewport": {"width": 1440, "height": 900},
        "screenshots": [
            {"path": "s1.jpg", "scrollY": 0, "naturalWidth": 1440, "naturalHeight": 900},
            {"path": "s2.jpg", "scrollY": 900, "naturalWidth": 1440, "naturalHeight": 900},
        ],
        "sections": [
            {"slug": "hero", "scroll_y_top": 0, "scroll_y_bottom": 899, "screenshot_ref": "s1.jpg"},
            {"slug": "footer", "scroll_y_top": 900, "scroll_y_bottom": 1799, "screenshot_ref": "s2.jpg"},
        ],
        "elements": [
            {"e_index": "e0", "rect": {"x": 40, "y": 100, "width": 300, "height": 60}},
        ],
    }


def _unplaceable_finding(index=1):
    """Absent finding with no proposed_anchor and no surface -> falls to Strategy 4."""
    return {
        "index": index,
        "f_ref": "trust-credibility/F-09",
        "baton_index": "absent",
        "priority": "HIGH",
        # deliberately no proposed_anchor, no surface/section
    }


class TestUnplacedMapping(unittest.TestCase):
    def test_strategy4_emits_no_position(self):
        mappings = auto_map_markers_v2([_unplaceable_finding()], _baton())
        self.assertEqual(len(mappings), 1)
        m = mappings[0]
        self.assertEqual(m["match_method"], "unplaced")
        self.assertIsNone(m["fallback_position"], "unplaced must carry NO position (blank)")
        self.assertIsNone(m["baton_element_index"])
        self.assertEqual(m["fallback_role"], "absent_unplaced")

    def test_no_marker_is_rendered_for_unplaced(self):
        findings = [_unplaceable_finding()]
        mappings = auto_map_markers_v2(findings, _baton())
        slide_markers = compute_marker_positions_v2(mappings, _baton())
        # The unplaced f_ref must not appear as a rendered marker on any slide.
        all_refs = {
            mk.get("f_ref")
            for markers in slide_markers.values()
            for mk in markers
        }
        self.assertNotIn("trust-credibility/F-09", all_refs)

    def test_visual_evidence_footprint_matches_old_banner(self):
        # page_level/low preserves the prior banner Phase-3 gate behavior.
        ve = derive_visual_evidence(match_method="unplaced")
        self.assertEqual(ve["type"], "page_level")
        self.assertEqual(ve["confidence"], "low")


class TestUnplacedReviewState(unittest.TestCase):
    def test_confidence_queues_for_manual_placement(self):
        self.assertEqual(_hotspot_confidence("unplaced"), "needs-manual-marker")

    def test_unplaced_marker_is_blank_and_hidden(self):
        marker = _unplaced_marker(
            "marker-x", "trust-credibility/F-09", "laptop-section-1", "high", None
        )
        self.assertTrue(marker["hidden"])
        self.assertEqual(marker["shape"], "point")
        self.assertEqual(marker["source"], "manual")
        for coord in ("cx_pct", "cy_pct", "x_pct", "y_pct", "w_pct", "h_pct"):
            self.assertNotIn(coord, marker, f"blank marker must not carry {coord}")

    def test_hidden_marker_renders_nothing(self):
        marker = _unplaced_marker(
            "marker-x", "trust-credibility/F-09", "laptop-section-1", "high", None
        )
        self.assertEqual(_render_marker_svg(marker, {"f_ref": "trust-credibility/F-09"}), "")

    def test_placed_finding_still_renders(self):
        # Guard against over-broadening: a normal e_index finding is unaffected.
        baton = _baton()
        findings = [{
            "index": 2,
            "f_ref": "visual-cta/F-01",
            "baton_index": "e0",
            "priority": "HIGH",
        }]
        mappings = auto_map_markers_v2(findings, baton)
        self.assertEqual(mappings[0]["match_method"], "e_index_lookup")
        slide_markers = compute_marker_positions_v2(mappings, baton)
        all_refs = {
            mk.get("f_ref")
            for markers in slide_markers.values()
            for mk in markers
        }
        self.assertIn("visual-cta/F-01", all_refs)


if __name__ == "__main__":
    unittest.main()
