"""Regression test for G14: rect coordinates must be clamped to >=0 at the source.

Off-canvas / partially-scrolled elements yield negative `getBoundingClientRect`
coordinates (observed `rect.x = -13` in the 2026-05-26 live run). `schema/baton-
v1.json` sets `rect.x/y/width/height` `minimum: 0`, so an unclamped baton fails
schema validation and the lead has to clamp by hand. The fix clamps at every
extraction/build site rather than relaxing the schema.

Sites covered (browser-free):
  - acquirer path: `_dpr_scale_element_css_to_phys` (behavioral)
  - acquirer path JS + Claude acquirer JS: `Math.max(0, ...)` in the extraction
  - v1->v2 converter: `max(0.0, ...)` in the rect builder (baton_v1_to_v2.py)
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import acquire_url as cb  # noqa: E402


class TestDprScaleClamp(unittest.TestCase):
    def test_negative_coords_clamp_to_zero(self):
        el = {"x": -13, "y": -4, "width": 180, "height": 40}
        out = cb._dpr_scale_element_css_to_phys(el, 1)
        self.assertEqual(out["x"], 0)
        self.assertEqual(out["y"], 0)
        # Non-negative dims survive (and scale).
        self.assertEqual(out["width"], 180)
        self.assertEqual(out["height"], 40)

    def test_positive_coords_scale_normally(self):
        el = {"x": 10, "y": 20, "width": 30, "height": 40}
        out = cb._dpr_scale_element_css_to_phys(el, 3)
        self.assertEqual((out["x"], out["y"], out["width"], out["height"]), (30, 60, 90, 120))


class TestExtractionJsClamps(unittest.TestCase):
    """The JS that runs in-browser must clamp at the source, not after."""

    def test_acquire_md_clamps_xy(self):
        doc = (REPO / "workflows" / "acquire.md").read_text(encoding="utf-8")
        self.assertIn("Math.max(0, Math.round(r.left))", doc)
        self.assertIn("Math.max(0, Math.round(r.top + scrollY))", doc)

    def test_cursor_elements_js_clamps_xy(self):
        src = (REPO / "scripts" / "acquire_url.py").read_text(encoding="utf-8")
        self.assertIn("Math.max(0, Math.round(r.left))", src)
        self.assertIn("Math.max(0, Math.round(r.top + scrollY))", src)


class TestConverterClamps(unittest.TestCase):
    def test_v1_to_v2_converter_clamps_rect(self):
        # Source-level guard on the durable converter that superseded
        # adapt_v1_baton_to_v2.py. Behavioral coverage of the same invariant
        # lives in tests/test_baton_v1_to_v2.py::TestElements.
        src = (REPO / "scripts" / "baton_v1_to_v2.py").read_text(encoding="utf-8")
        self.assertIn('max(0.0, float(el.get("x", 0)))', src)
        self.assertIn('max(0.0, float(el.get("y", 0)))', src)


if __name__ == "__main__":
    unittest.main()
