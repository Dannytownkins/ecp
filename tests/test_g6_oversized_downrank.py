"""G6 (product.md §4.2 precision-first) — oversized exact-element hotspots are
auto-down-ranked to approximate proxies.

An exact_element marker whose baton rect spans most of the viewport is almost
always anchored to a parent container (full header/drawer/body), not the subject
element. Rendering it as a solid "exact" rect overclaims precision. This locks in:

- auto_map_markers_v2 down-ranks an oversized exact_element mapping to
  proxy_element (renders dashed) while leaving normal-sized exacts alone.
- the down-rank threshold equals the giant_exact_rectangles gate threshold, so
  after down-ranking that gate reports zero violations.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts"))

from report.v2_markers import (  # noqa: E402
    GIANT_EXACT_HEIGHT_PCT,
    GIANT_EXACT_WIDTH_PCT,
    auto_map_markers_v2,
    compute_marker_positions_v2,
)
from assembly.visual_quality import (  # noqa: E402
    DEFAULT_GIANT_HEIGHT_PCT,
    DEFAULT_GIANT_WIDTH_PCT,
    check_giant_exact_rectangles,
)


def _baton(elements):
    return {
        "device": "laptop",
        "viewport": {"width": 1440, "height": 900},
        "screenshots": [
            {"path": "s1.jpg", "scrollY": 0, "naturalWidth": 1440, "naturalHeight": 900},
        ],
        "sections": [
            {"slug": "hero", "scroll_y_top": 0, "scroll_y_bottom": 899, "screenshot_ref": "s1.jpg"},
        ],
        "elements": elements,
    }


def _finding(index, f_ref):
    return {"index": index, "f_ref": f_ref, "baton_index": f"e{index}", "priority": "HIGH"}


def _ve_by_ref(mappings):
    return {m["f_ref"]: (m.get("visual_evidence") or {}) for m in mappings}


class TestThresholdSync(unittest.TestCase):
    def test_downrank_threshold_matches_gate(self):
        # If these drift, down-ranking would not actually clear the gate.
        self.assertEqual(GIANT_EXACT_WIDTH_PCT, DEFAULT_GIANT_WIDTH_PCT)
        self.assertEqual(GIANT_EXACT_HEIGHT_PCT, DEFAULT_GIANT_HEIGHT_PCT)


class TestOversizedDownRank(unittest.TestCase):
    def test_normal_element_stays_exact(self):
        # 300x60 of a 1440x900 viewport -> ~21%w / ~7%h: well under threshold.
        baton = _baton([{"e_index": "e0", "rect": {"x": 40, "y": 100, "width": 300, "height": 60}}])
        mappings = auto_map_markers_v2([_finding(0, "visual-cta/F-01")], baton)
        ve = _ve_by_ref(mappings)["visual-cta/F-01"]
        self.assertEqual(ve["type"], "exact_element")
        self.assertEqual(ve["confidence"], "high")

    def test_wide_element_is_downranked(self):
        # 1380 wide of 1440 -> ~96%w: a full-width container.
        baton = _baton([{"e_index": "e0", "rect": {"x": 10, "y": 100, "width": 1380, "height": 80}}])
        mappings = auto_map_markers_v2([_finding(0, "visual-cta/F-01")], baton)
        ve = _ve_by_ref(mappings)["visual-cta/F-01"]
        self.assertEqual(ve["type"], "proxy_element")
        self.assertEqual(ve["confidence"], "low")
        self.assertIn("down-ranked", ve["reason"].lower())

    def test_tall_element_is_downranked(self):
        # 700 tall of 900 -> ~78%h: exceeds the 70%h height threshold.
        baton = _baton([{"e_index": "e0", "rect": {"x": 40, "y": 0, "width": 300, "height": 700}}])
        mappings = auto_map_markers_v2([_finding(0, "trust-credibility/F-02")], baton)
        ve = _ve_by_ref(mappings)["trust-credibility/F-02"]
        self.assertEqual(ve["type"], "proxy_element")

    def test_gate_passes_after_downrank(self):
        # A giant element that previously tripped the giant_exact gate now
        # renders as a proxy, so the gate reports zero exact-rect violations.
        baton = _baton([{"e_index": "e0", "rect": {"x": 5, "y": 50, "width": 1400, "height": 820}}])
        findings = [_finding(0, "visual-cta/F-01")]
        mappings = auto_map_markers_v2(findings, baton)
        slide_markers = compute_marker_positions_v2(mappings, baton)
        markers = [mk for marks in slide_markers.values() for mk in marks]
        result = check_giant_exact_rectangles(markers)
        self.assertTrue(result["passed"], result["summary"])
        self.assertEqual(result["detail"]["violation_count"], 0)


if __name__ == "__main__":
    unittest.main()
