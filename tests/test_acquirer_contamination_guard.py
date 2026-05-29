"""Regression: acquire_url.py cross-engagement contamination guard.

The 2026-05-27 four-concurrent-audits batch surfaced a real failure
mode: ``docs/ecp/2026-05-27-4a0721e9`` (a slingmods.com audit) captured
51 Amazon "Sponsored / Nordic Naturals" elements because the headless
browser session drifted to amazon.com mid-extraction (a concurrent
``docs/ecp/2026-05-27-0669899d`` audit was navigating there). The
contamination only surfaced because two specialists independently flagged
"baton elements look like Amazon" — there was no acquisition-side guard.

Post-fix (this branch): ``_build_elements_js`` bakes a hostname check
into the per-section extraction JS that aborts to a contamination
sentinel if ``window.location.hostname`` doesn't match the expected one.
``_check_for_contamination`` detects the sentinel; the calling acquirer
returns exit 1 with a loud STATUS line instead of silently capturing
elements from the wrong page.

unittest-style for ``python -m unittest discover`` runner compatibility.

Run:
    python -m unittest tests.test_acquirer_contamination_guard
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent


def _load_acquire_url():
    """Load the canonical acquirer module (scripts/acquire_url.py) by path."""
    spec = importlib.util.spec_from_file_location(
        "acquire_url",
        _REPO / "scripts" / "acquire_url.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclass decorator at module load needs sys.modules registration.
    sys.modules["acquire_url"] = module
    spec.loader.exec_module(module)
    return module


class TestBuildElementsJsHostnameGuard(unittest.TestCase):
    def setUp(self):
        self.cb = _load_acquire_url()

    def test_hostname_inlined_as_json_string_literal(self):
        js = self.cb._build_elements_js("slingmods.com")
        # The hostname is inlined as a JS string literal — JSON-quoted so
        # special characters can't break out of the string boundary.
        self.assertIn('"slingmods.com"', js)
        self.assertIn("__contamination_detected", js)
        self.assertIn("window.location && window.location.hostname", js)

    def test_dangerous_hostname_chars_are_json_escaped(self):
        """A hostname containing an unescaped " or ; would otherwise break
        out of the string literal and execute as JS. JSON encoding handles
        this — verify the injection vector is closed."""
        js = self.cb._build_elements_js('evil.com"; alert(1); //')
        # The dangerous payload must appear inside an escaped JSON string,
        # not as raw JS. The raw form ('"; alert(1)') should be absent.
        # The escaped form ('\"') should be present, indicating the JSON
        # serializer escaped the inner quote.
        self.assertNotIn('evil.com"; alert(1)', js)
        self.assertIn('evil.com\\"; alert(1); //', js)


class TestCheckForContamination(unittest.TestCase):
    def setUp(self):
        self.cb = _load_acquire_url()

    def test_returns_none_on_normal_element_list(self):
        self.assertIsNone(self.cb._check_for_contamination([{"tag": "h1"}]))

    def test_returns_none_on_none_input(self):
        self.assertIsNone(self.cb._check_for_contamination(None))

    def test_returns_none_on_unrelated_dict(self):
        self.assertIsNone(
            self.cb._check_for_contamination({"not_a_sentinel": True})
        )

    def test_returns_sentinel_when_contamination_flag_set(self):
        sentinel = {
            "__contamination_detected": True,
            "expected_hostname": "slingmods.com",
            "actual_hostname": "amazon.com",
            "actual_href": "https://www.amazon.com/dp/B002CQU54Q",
        }
        got = self.cb._check_for_contamination(sentinel)
        self.assertIs(got, sentinel)
        self.assertEqual(got["actual_hostname"], "amazon.com")

    def test_returns_none_when_flag_is_falsy(self):
        """A literal `False` flag must not trigger the contamination
        path — sentinel-by-truthiness."""
        sentinel_off = {
            "__contamination_detected": False,
            "expected_hostname": "slingmods.com",
            "actual_hostname": "slingmods.com",
            "actual_href": "https://www.slingmods.com/stinger",
        }
        self.assertIsNone(self.cb._check_for_contamination(sentinel_off))


class TestElementsJsConstantRemoved(unittest.TestCase):
    """The module-level ``_ELEMENTS_JS`` constant was replaced by the
    ``_build_elements_js(expected_hostname)`` function so the hostname
    guard can be inlined. If a future change re-introduces the constant,
    this regression catches it and forces an explicit choice about
    whether the new caller also gets the contamination guard."""

    def test_old_constant_is_gone(self):
        cb = _load_acquire_url()
        self.assertFalse(
            hasattr(cb, "_ELEMENTS_JS"),
            "Old _ELEMENTS_JS module constant has been replaced by "
            "_build_elements_js(expected_hostname); a re-introduced "
            "constant would bypass the contamination guard.",
        )


if __name__ == "__main__":
    unittest.main()
