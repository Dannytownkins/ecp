"""v2 unit tests: assembly.canary_checks (Phase I substantive canaries).

Three canaries the audit lead runs at audit completion:

1. ethics_findings_have_source_urls — every BLOCK/ADJACENT carries a
   source_url that's not a self-cite of the audited domain.
2. element_index_match_rate — at least 80 percent of ELEMENT lines cite a
   baton element index.
3. cross_device_ethics_diff — desktop and mobile audits surface the same
   set of ethics findings within max_diff tolerance.

Run:
    python -m unittest tests.test_v2_canary_checks
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts"))

from assembly.canary_checks import (  # noqa: E402
    check_cross_device_ethics_diff,
    check_element_index_match_rate,
    check_ethics_findings_have_source_urls,
    run_all_canaries,
    _domain_of,
)


class TestEthicsSourceUrlCanary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, payload: dict) -> Path:
        path = self.tmp_path / "ethics-findings.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_missing_file_fails_softly(self):
        result = check_ethics_findings_have_source_urls(
            self.tmp_path / "does-not-exist.json"
        )
        self.assertFalse(result["passed"])
        self.assertTrue(result["detail"]["file_missing"])

    def test_unreadable_json_fails(self):
        path = self.tmp_path / "ethics-findings.json"
        path.write_text("{not valid json", encoding="utf-8")
        result = check_ethics_findings_have_source_urls(path)
        self.assertFalse(result["passed"])
        self.assertIn("parse_error", result["detail"])

    def test_all_clear_findings_pass_trivially(self):
        path = self._write({
            "findings": [
                {"local_id": 1, "ethics_state": "CLEAR", "title": "X"},
                {"local_id": 2, "ethics_state": "CLEAR", "title": "Y"},
            ]
        })
        result = check_ethics_findings_have_source_urls(path)
        self.assertTrue(result["passed"])
        self.assertEqual(result["detail"]["clear_count"], 2)
        self.assertEqual(result["detail"]["total_actionable"], 0)

    def test_block_finding_with_source_url_passes(self):
        path = self._write({
            "findings": [
                {
                    "local_id": 1,
                    "ethics_state": "BLOCK",
                    "title": "Fake review",
                    "source_url": "https://www.ftc.gov/legal-library/browse/rules/16-cfr-part-465",
                },
            ]
        })
        result = check_ethics_findings_have_source_urls(
            path, audited_domain="slingmods.com"
        )
        self.assertTrue(result["passed"])

    def test_block_finding_missing_source_url_fails(self):
        path = self._write({
            "findings": [
                {"local_id": 1, "ethics_state": "BLOCK", "title": "X"},
            ]
        })
        result = check_ethics_findings_have_source_urls(path)
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["detail"]["missing_source_url"]), 1)
        self.assertEqual(
            result["detail"]["missing_source_url"][0]["f_ref"], "ethics F-01"
        )

    def test_adjacent_finding_missing_source_url_fails(self):
        path = self._write({
            "findings": [
                {"local_id": 7, "ethics_state": "ADJACENT", "title": "X"},
            ]
        })
        result = check_ethics_findings_have_source_urls(path)
        self.assertFalse(result["passed"])

    def test_self_cite_filler_detected(self):
        path = self._write({
            "findings": [
                {
                    "local_id": 1,
                    "ethics_state": "BLOCK",
                    "title": "X",
                    "source_url": "https://www.slingmods.com/some-page",
                },
            ]
        })
        result = check_ethics_findings_have_source_urls(
            path, audited_domain="slingmods.com"
        )
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["detail"]["self_cite_filler"]), 1)

    def test_self_cite_subdomain_also_detected(self):
        path = self._write({
            "findings": [
                {
                    "local_id": 1,
                    "ethics_state": "BLOCK",
                    "title": "X",
                    "source_url": "https://shop.slingmods.com/legal",
                },
            ]
        })
        result = check_ethics_findings_have_source_urls(
            path, audited_domain="slingmods.com"
        )
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["detail"]["self_cite_filler"]), 1)

    def test_skips_self_cite_check_when_audited_domain_none(self):
        path = self._write({
            "findings": [
                {
                    "local_id": 1,
                    "ethics_state": "BLOCK",
                    "title": "X",
                    "source_url": "https://www.slingmods.com/some-page",
                },
            ]
        })
        result = check_ethics_findings_have_source_urls(path, audited_domain=None)
        # Without audited_domain, self-cite check skipped — passes since source_url is present
        self.assertTrue(result["passed"])

    def test_clear_finding_without_source_url_does_not_fail(self):
        path = self._write({
            "findings": [
                {"local_id": 1, "ethics_state": "CLEAR", "title": "X"},
                {"local_id": 2, "ethics_state": "CLEAR", "title": "Y"},
            ]
        })
        result = check_ethics_findings_have_source_urls(
            path, audited_domain="slingmods.com"
        )
        self.assertTrue(result["passed"])

    def test_mixed_states_partial_failure(self):
        path = self._write({
            "findings": [
                {"local_id": 1, "ethics_state": "CLEAR"},
                {
                    "local_id": 2,
                    "ethics_state": "BLOCK",
                    "title": "good",
                    "source_url": "https://www.ftc.gov/x",
                },
                {"local_id": 3, "ethics_state": "BLOCK", "title": "bad"},  # missing
            ]
        })
        result = check_ethics_findings_have_source_urls(path)
        self.assertFalse(result["passed"])
        self.assertEqual(result["detail"]["total_actionable"], 2)
        self.assertEqual(len(result["detail"]["missing_source_url"]), 1)


class TestDomainOfHelper(unittest.TestCase):
    def test_full_url(self):
        self.assertEqual(_domain_of("https://www.example.com/path"), "example.com")

    def test_strips_www(self):
        self.assertEqual(_domain_of("https://www.SLINGMODS.com/x"), "slingmods.com")

    def test_no_protocol(self):
        self.assertEqual(_domain_of("slingmods.com/x"), "slingmods.com")

    def test_subdomain_preserved(self):
        self.assertEqual(_domain_of("https://shop.slingmods.com"), "shop.slingmods.com")

    def test_empty_input(self):
        self.assertEqual(_domain_of(""), "")
        self.assertEqual(_domain_of(None or ""), "")


class TestElementIndexMatchRateCanary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_audit(self, name: str, content: str) -> Path:
        path = self.tmp_path / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_empty_input_list_fails(self):
        result = check_element_index_match_rate([])
        self.assertFalse(result["passed"])
        self.assertTrue(result["detail"]["empty_input"])

    def test_all_at_e_pattern_passes(self):
        content = (
            "### pricing F-01 — Test\n\n"
            "**ELEMENT:** `div.price` at e5 (y=403)\n"
            "**ELEMENT:** `button` at e23 (y=120)\n"
            "**ELEMENT:** `span` at e10 (y=80)\n"
        )
        path = self._write_audit("audit-desktop.md", content)
        result = check_element_index_match_rate([path])
        self.assertTrue(result["passed"])
        self.assertEqual(result["detail"]["rate"], 1.0)
        self.assertEqual(result["detail"]["matched"], 3)
        self.assertEqual(result["detail"]["total_elements"], 3)

    def test_all_absent_lines_fail_no_present_elements(self):
        # No present elements at all — rate is 0.0, canary fails (the
        # audit has nothing to measure baton_index coverage against).
        content = (
            "**ELEMENT:** (absent — proposed location: above hero)\n"
            "**ELEMENT:** (absent — proposed location: footer)\n"
            "**ELEMENT:** (absent — proposed location: head)\n"
        )
        path = self._write_audit("audit-desktop.md", content)
        result = check_element_index_match_rate([path])
        self.assertFalse(result["passed"])
        self.assertEqual(result["detail"]["rate"], 0.0)
        self.assertEqual(result["detail"]["absent"], 3)
        self.assertEqual(result["detail"]["present_elements"], 0)

    def test_absent_lines_excluded_from_denominator(self):
        # 8 lines with at eN + 2 absent. Rate = 8/8 (present) = 1.0.
        # Absent findings are SEMANTICALLY correct without baton_index;
        # the canary is checking "of findings that claim a real element,
        # do they cite baton_index?"
        lines = [f"**ELEMENT:** `tag` at e{i} (y=0)" for i in range(8)]
        lines += ["**ELEMENT:** (absent — proposed location: x)"] * 2
        path = self._write_audit("audit-desktop.md", "\n".join(lines))
        result = check_element_index_match_rate([path], threshold=0.8)
        self.assertTrue(result["passed"])
        self.assertEqual(result["detail"]["rate"], 1.0)
        self.assertEqual(result["detail"]["absent"], 2)
        self.assertEqual(result["detail"]["present_elements"], 8)

    def test_absent_without_parens_excluded(self):
        # Phase K (2026-04-29) regression: Phase J D2 fixture wrapped
        # absent in parens but Phase K dispatch surfaced synth output
        # using "absent — proposed location" without parens. Both
        # forms are semantically identical; both must be excluded from
        # the denominator. Without this, gate run-01 produced
        # element_index_match_rate=0.507 (false drift) when the synth's
        # actual format compliance was 1.000.
        lines = [f"**ELEMENT:** `tag` at e{i} (y=0)" for i in range(8)]
        lines += ["**ELEMENT:** absent — proposed location: above hero"] * 2
        lines += ["**ELEMENT:** absent — between description and footer"]
        path = self._write_audit("audit-desktop.md", "\n".join(lines))
        result = check_element_index_match_rate([path], threshold=0.8)
        self.assertTrue(result["passed"], result["summary"])
        self.assertEqual(result["detail"]["rate"], 1.0)
        self.assertEqual(result["detail"]["absent"], 3)
        self.assertEqual(result["detail"]["present_elements"], 8)

    def test_g20_absent_lines_with_at_eN_in_proposed_anchor_do_not_inflate_rate(self):
        """G20 (2026-05-27): pre-fix, the canary counted `at eN` matches
        across the WHOLE element-line list but only excluded absent lines
        from the denominator. Absent findings often phrase their
        proposed-anchor prose as `(absent — proposed location: ... at e3)`,
        so the `at eN` token appeared on lines the denominator dropped —
        making the numerator exceed the denominator and producing
        impossible rate values like 1.23.

        Live evidence: docs/ecp/2026-05-27-625832a6 lead-reflection
        reported `element_index_match_rate=1.23`, which is mathematically
        impossible for a rate. Post-fix: `matched` only counts non-absent
        lines, so rate is bounded by [0, 1.0]."""
        # 4 present-element lines with at eN + 3 absent lines whose
        # proposed-anchor prose ALSO contains `at eN`. Pre-fix:
        # matched=7, present=4, rate=1.75. Post-fix: matched=4,
        # present=4, rate=1.0.
        lines = [f"**ELEMENT:** `tag` at e{i} (y=0)" for i in range(4)]
        lines += [
            "**ELEMENT:** (absent — proposed location: near header at e10)",
            "**ELEMENT:** absent — proposed location: section-bottom at e22",
            "**ELEMENT:** (absent — proposed location: viewport-sticky at e99)",
        ]
        path = self._write_audit("audit-desktop.md", "\n".join(lines))
        result = check_element_index_match_rate([path], threshold=0.8)
        self.assertTrue(result["passed"], result["summary"])
        self.assertLessEqual(
            result["detail"]["rate"],
            1.0,
            f"G20: rate must be bounded by [0, 1.0]; absent-line `at eN` "
            f"mentions must not leak into the numerator. "
            f"Got rate={result['detail']['rate']!r}, summary={result['summary']!r}",
        )
        self.assertEqual(result["detail"]["rate"], 1.0)
        self.assertEqual(result["detail"]["present_elements"], 4)
        self.assertEqual(result["detail"]["matched"], 4)
        self.assertEqual(result["detail"]["absent"], 3)

    def test_present_element_without_baton_fails(self):
        # The regression case: synthesizer emits an element description
        # without an "at eN" reference and without an explicit absent
        # marker — a present-on-page element described by tag/role/text
        # but missing the locked ELEMENT format's baton_index citation.
        # 6 lines with at eN + 4 lines describing element without baton = 6/10 = 0.6.
        lines = [f"**ELEMENT:** `tag` at e{i} (y=0)" for i in range(6)]
        lines += ["**ELEMENT:** product description body copy below buy box"] * 4
        path = self._write_audit("audit-desktop.md", "\n".join(lines))
        result = check_element_index_match_rate([path], threshold=0.8)
        self.assertFalse(result["passed"])
        self.assertAlmostEqual(result["detail"]["rate"], 0.6)
        self.assertEqual(result["detail"]["absent"], 0)

    def test_off_baton_phrasing_excluded(self):
        # Lines explicitly noting element is on-page but not in baton
        # are excluded from the denominator — the baton is a curated
        # subset, not a full DOM dump. Specialist describes by tag/text
        # when baton coverage is incomplete.
        lines = [
            "**ELEMENT:** `tag` at e1 (y=0)",
            "**ELEMENT:** `tag` at e2 (y=0)",
            "**ELEMENT:** `tag` at e3 (y=0)",
            "**ELEMENT:** hero product `<img>` (absent from baton)",
            "**ELEMENT:** breadcrumb (not in baton)",
            "**ELEMENT:** gallery thumbnails (no baton entry)",
            "**ELEMENT:** product spec table (absent from baton element index)",
        ]
        path = self._write_audit("audit-desktop.md", "\n".join(lines))
        result = check_element_index_match_rate([path], threshold=0.8)
        self.assertTrue(result["passed"])
        self.assertEqual(result["detail"]["absent"], 4)
        self.assertEqual(result["detail"]["present_elements"], 3)
        self.assertEqual(result["detail"]["matched"], 3)

    def test_missing_file_tolerated(self):
        path = self.tmp_path / "audit-desktop.md"
        # File doesn't exist
        result = check_element_index_match_rate([path])
        self.assertFalse(result["passed"])
        self.assertEqual(result["detail"]["per_file"][0]["exists"], False)

    def test_aggregates_across_multiple_files(self):
        # Desktop: 1 present-with-baton + 1 absent
        # Mobile: 2 present-with-baton
        # Aggregate: 3 matched / 3 present (1 absent excluded) = 1.0
        desktop = self._write_audit(
            "audit-desktop.md",
            "**ELEMENT:** `tag` at e1 (y=0)\n**ELEMENT:** (absent)\n",
        )
        mobile = self._write_audit(
            "audit-mobile.md",
            "**ELEMENT:** `tag` at e2 (y=0)\n**ELEMENT:** `tag` at e3 (y=0)\n",
        )
        result = check_element_index_match_rate([desktop, mobile])
        self.assertTrue(result["passed"])
        self.assertEqual(result["detail"]["total_elements"], 4)
        self.assertEqual(result["detail"]["present_elements"], 3)
        self.assertEqual(result["detail"]["matched"], 3)
        self.assertEqual(result["detail"]["absent"], 1)

    def test_at_eN_in_middle_of_line_matches(self):
        content = "**ELEMENT:** `div.foo` at e7 (y=403, height=42 CSS px)\n"
        path = self._write_audit("audit-desktop.md", content)
        result = check_element_index_match_rate([path])
        self.assertTrue(result["passed"])

    def test_word_at_without_e_prefix_does_not_match(self):
        content = "**ELEMENT:** lorem ipsum at the top of page\n"
        path = self._write_audit("audit-desktop.md", content)
        result = check_element_index_match_rate([path])
        self.assertFalse(result["passed"])

    def test_zero_elements_fails(self):
        # No ELEMENT lines at all — total=0 means rate=0, fails
        path = self._write_audit("audit-desktop.md", "Some content with no elements\n")
        result = check_element_index_match_rate([path])
        self.assertFalse(result["passed"])
        self.assertEqual(result["detail"]["total_elements"], 0)
        self.assertEqual(result["detail"]["present_elements"], 0)


class TestCrossDeviceEthicsDiffCanary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_audit(self, name: str, content: str) -> Path:
        path = self.tmp_path / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_both_audits_zero_ethics_passes(self):
        desktop = self._write_audit("audit-desktop.md", "### pricing F-01 — X\n")
        mobile = self._write_audit("audit-mobile.md", "### pricing F-01 — X\n")
        result = check_cross_device_ethics_diff(desktop, mobile)
        self.assertTrue(result["passed"])
        self.assertEqual(result["detail"]["diff"], 0)

    def test_same_ethics_findings_pass(self):
        content = (
            "### ethics F-01 — Issue 1\n\nbody\n\n"
            "### ethics F-02 — Issue 2\n\nbody\n"
        )
        desktop = self._write_audit("audit-desktop.md", content)
        mobile = self._write_audit("audit-mobile.md", content)
        result = check_cross_device_ethics_diff(desktop, mobile)
        self.assertTrue(result["passed"])
        self.assertEqual(result["detail"]["desktop_count"], 2)
        self.assertEqual(result["detail"]["mobile_count"], 2)

    def test_one_finding_difference_within_tolerance(self):
        desktop = self._write_audit(
            "audit-desktop.md",
            "### ethics F-01 — A\n### ethics F-02 — B\n",
        )
        mobile = self._write_audit(
            "audit-mobile.md",
            "### ethics F-01 — A\n",
        )
        result = check_cross_device_ethics_diff(desktop, mobile, max_diff=1)
        self.assertTrue(result["passed"])
        self.assertEqual(result["detail"]["diff"], 1)

    def test_two_findings_difference_fails(self):
        desktop = self._write_audit(
            "audit-desktop.md",
            "### ethics F-01\n### ethics F-02\n### ethics F-03\n",
        )
        mobile = self._write_audit("audit-mobile.md", "### ethics F-01\n")
        result = check_cross_device_ethics_diff(desktop, mobile, max_diff=1)
        self.assertFalse(result["passed"])
        self.assertEqual(result["detail"]["diff"], 2)

    def test_asymmetric_refs_listed(self):
        desktop = self._write_audit(
            "audit-desktop.md",
            "### ethics F-01 — A\n### ethics F-02 — B\n",
        )
        mobile = self._write_audit(
            "audit-mobile.md",
            "### ethics F-01 — A\n### ethics F-03 — C\n",
        )
        result = check_cross_device_ethics_diff(desktop, mobile)
        # Counts equal (2 vs 2) — passes the count diff test
        self.assertTrue(result["passed"])
        # But asymmetric_refs surfaces the divergence
        asymmetric_set = {(r["ref"], r["in"]) for r in result["detail"]["asymmetric_refs"]}
        self.assertIn(("ethics F-02", "desktop_only"), asymmetric_set)
        self.assertIn(("ethics F-03", "mobile_only"), asymmetric_set)

    def test_missing_files_count_as_zero(self):
        # Both files missing — diff=0, but counts also zero
        desktop = self.tmp_path / "missing-d.md"
        mobile = self.tmp_path / "missing-m.md"
        result = check_cross_device_ethics_diff(desktop, mobile)
        self.assertTrue(result["passed"])
        self.assertEqual(result["detail"]["desktop_count"], 0)
        self.assertEqual(result["detail"]["mobile_count"], 0)

    def test_h4_headings_also_count(self):
        # Some specialists may emit findings as level-4 headings
        desktop = self._write_audit(
            "audit-desktop.md",
            "#### ethics F-01 — X\n#### ethics F-02 — Y\n",
        )
        mobile = self._write_audit(
            "audit-mobile.md",
            "#### ethics F-01 — X\n#### ethics F-02 — Y\n",
        )
        result = check_cross_device_ethics_diff(desktop, mobile)
        self.assertTrue(result["passed"])
        self.assertEqual(result["detail"]["desktop_count"], 2)


class TestRunAllCanaries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engagement_dir = Path(self.tmp.name) / "docs" / "ecp" / "test-eng"
        self.engagement_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_pass_on_clean_engagement(self):
        # Ethics — all CLEAR (passes trivially)
        (self.engagement_dir / "ethics-findings.json").write_text(json.dumps({
            "findings": [
                {"local_id": 1, "ethics_state": "CLEAR", "title": "X"},
            ]
        }), encoding="utf-8")
        # Audit — all element lines have at eN
        audit_content = (
            "### pricing F-01 — Test\n\n"
            "**ELEMENT:** `div.price` at e5 (y=403)\n\n"
        )
        (self.engagement_dir / "audit-desktop.md").write_text(audit_content, encoding="utf-8")
        (self.engagement_dir / "audit-mobile.md").write_text(audit_content, encoding="utf-8")

        out = run_all_canaries(self.engagement_dir, audited_domain="slingmods.com")
        self.assertTrue(out["all_passed"])
        # Phase 6 (2026-05-18) added priority_path_count_parity as the
        # fourth canary; older runs expected 3. G16 (2026-05-27) added
        # clusters_represented as the fifth — it skips with PASS on
        # fixtures that don't have canonical-f-refs.json.
        # G22+G24 (2026-05-28) added trace_counters_reconcile_with_artifacts
        # as the sixth — it skips with PASS on fixtures without
        # audit-trace.log. visual_quality block adds zero results when no
        # review-state files are present (Phase 3 default-on path).
        self.assertEqual(len(out["results"]), 6)

    def test_aggregates_failure(self):
        # Ethics — block without source_url fails
        (self.engagement_dir / "ethics-findings.json").write_text(json.dumps({
            "findings": [
                {"local_id": 1, "ethics_state": "BLOCK", "title": "X"},  # no source_url
            ]
        }), encoding="utf-8")
        audit_content = "**ELEMENT:** `div` at e1 (y=0)\n"
        (self.engagement_dir / "audit-desktop.md").write_text(audit_content, encoding="utf-8")
        (self.engagement_dir / "audit-mobile.md").write_text(audit_content, encoding="utf-8")

        out = run_all_canaries(self.engagement_dir)
        self.assertFalse(out["all_passed"])
        # Verify ethics canary failed; element + cross-device passed
        results_by_name = {r["name"]: r for r in out["results"]}
        self.assertFalse(results_by_name["ethics_findings_have_source_urls"]["passed"])
        self.assertTrue(results_by_name["element_index_match_rate"]["passed"])
        self.assertTrue(results_by_name["cross_device_ethics_diff"]["passed"])


if __name__ == "__main__":
    unittest.main()
