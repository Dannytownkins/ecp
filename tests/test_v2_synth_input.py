"""v2 unit tests: synth_input helpers (Phase F.3).

Covers the three deterministic synthesizer-dispatch helpers:
1. trim_baton_to_referenced_elements + trim_baton_file
2. compute_phrasing_seeds + render_phrasing_seeds_block
3. levenshtein_distance / levenshtein_ratio / extract_finding_prose /
   assert_synchronization_invariant

Run:
    python -m unittest tests.test_v2_synth_input
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts"))

from assembly.models import EvidenceAnchor, Finding  # noqa: E402
from assembly.synth_input import (  # noqa: E402
    SYNCHRONIZATION_THRESHOLD,
    assert_synchronization_invariant,
    collect_referenced_e_indexes,
    compute_phrasing_seeds,
    extract_finding_prose,
    levenshtein_distance,
    levenshtein_ratio,
    render_phrasing_seeds_block,
    trim_baton_file,
    trim_baton_to_referenced_elements,
)


def _finding(
    *,
    cluster: str = "pricing",
    device: str = "mobile",
    local_index: int = 1,
    title: str = "Test Finding",
    scope: str = "page",
    baton_index: str = "e7",
    priority: str = "MEDIUM",
    tier: str = "Silver",
    confidence: float | None = 0.85,
    observation: str = "The price block has no anchor.",
    recommendation: str = "Add an MSRP strikethrough above the live price.",
    why_matters: str = "Anchoring lifts perceived value.",
    anchors: tuple[EvidenceAnchor, ...] = (),
) -> Finding:
    """Build a Finding for tests."""
    priority_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}[priority]
    return Finding(
        cluster=cluster,
        device=device,
        local_index=local_index,
        verdict="FAIL",
        section="price-block",
        element="$69.95",
        element_normalized="$69.95",
        source="VISUAL",
        priority=priority,
        priority_rank=priority_rank,
        observation=observation,
        recommendation=recommendation,
        reference="price-anchoring.md",
        title=title,
        why_matters=why_matters,
        citation="price-anchoring.md",
        tier=tier,
        scope=scope,
        change_type="copy",
        change_scope="single-file",
        evidence_anchors=anchors,
        confidence=confidence,
        baton_index=baton_index,
        surface="price-block",
    )


class TestCollectReferencedEIndexes(unittest.TestCase):
    def test_collects_baton_index_field(self):
        f = _finding(baton_index="e7")
        refs = collect_referenced_e_indexes([f])
        self.assertEqual(refs, {"e7"})

    def test_collects_dom_anchor_references(self):
        f = _finding(
            baton_index="e7",
            anchors=(
                EvidenceAnchor(type="dom", reference="e8"),
                EvidenceAnchor(type="visual", reference="section-2-mobile.jpg"),
                EvidenceAnchor(type="both", reference="e9"),
            ),
        )
        refs = collect_referenced_e_indexes([f])
        self.assertEqual(refs, {"e7", "e8", "e9"})

    def test_skips_absent_baton_index(self):
        f = _finding(baton_index="absent")
        refs = collect_referenced_e_indexes([f])
        self.assertEqual(refs, set())

    def test_skips_visual_anchor_references(self):
        f = _finding(
            baton_index="e7",
            anchors=(EvidenceAnchor(type="visual", reference="section-2-mobile.jpg"),),
        )
        refs = collect_referenced_e_indexes([f])
        self.assertEqual(refs, {"e7"})

    def test_skips_non_e_index_dom_references(self):
        # CSS-selector dom anchors (rare; emitted when finding's element has no
        # baton e_index) are filtered out — they can't be resolved anyway.
        f = _finding(
            baton_index="e7",
            anchors=(EvidenceAnchor(type="dom", reference="div.review-snippet"),),
        )
        refs = collect_referenced_e_indexes([f])
        self.assertEqual(refs, {"e7"})

    def test_unions_across_findings(self):
        f1 = _finding(local_index=1, baton_index="e7")
        f2 = _finding(local_index=2, baton_index="e10")
        f3 = _finding(local_index=3, baton_index="absent")
        refs = collect_referenced_e_indexes([f1, f2, f3])
        self.assertEqual(refs, {"e7", "e10"})


class TestTrimBatonToReferencedElements(unittest.TestCase):
    def _baton(self, e_indexes: list[str]) -> dict:
        return {
            "schema_version": 1,
            "engagement_id": "2026-04-27-aaaaaaaa",
            "device": "mobile",
            "url": "https://example.com",
            "captured_at": "2026-04-27T16:00:00.000Z",
            "viewport": {"width": 390, "height": 844, "dpr_requested": 3, "dpr_actual": 3},
            "capture_state": {
                "hydration": "post-hydration",
                "overlays_detected": [],
                "page_height_px": 5000,
            },
            "elements": [{"e_index": e, "tag": "div"} for e in e_indexes],
            "sections": [],
            "page_head": {},
        }

    def test_filters_to_referenced_elements(self):
        baton = self._baton(["e1", "e2", "e3", "e4", "e5"])
        trimmed = trim_baton_to_referenced_elements(baton, {"e1", "e3", "e5"})
        kept = [el["e_index"] for el in trimmed["elements"]]
        self.assertEqual(kept, ["e1", "e3", "e5"])  # preserves DOM order

    def test_preserves_other_top_level_fields(self):
        baton = self._baton(["e1", "e2"])
        trimmed = trim_baton_to_referenced_elements(baton, {"e1"})
        self.assertEqual(trimmed["engagement_id"], baton["engagement_id"])
        self.assertEqual(trimmed["viewport"], baton["viewport"])
        self.assertEqual(trimmed["capture_state"], baton["capture_state"])

    def test_empty_referenced_set_yields_empty_elements(self):
        baton = self._baton(["e1", "e2"])
        trimmed = trim_baton_to_referenced_elements(baton, set())
        self.assertEqual(trimmed["elements"], [])

    def test_referenced_index_not_in_baton_silently_skipped(self):
        # A finding may cite e99 even if the baton only has e1..e5 (bug class
        # the business-rules layer catches separately). Trim should not raise.
        baton = self._baton(["e1", "e2"])
        trimmed = trim_baton_to_referenced_elements(baton, {"e1", "e99"})
        self.assertEqual([el["e_index"] for el in trimmed["elements"]], ["e1"])

    def test_determinism(self):
        # Same input → byte-identical output across runs.
        baton = self._baton(["e1", "e2", "e3"])
        a = trim_baton_to_referenced_elements(baton, {"e2", "e3"})
        b = trim_baton_to_referenced_elements(baton, {"e2", "e3"})
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_trim_baton_file_round_trip(self):
        baton = self._baton(["e1", "e2", "e3", "e4"])
        f1 = _finding(local_index=1, baton_index="e2")
        f2 = _finding(
            local_index=2,
            baton_index="absent",
            anchors=(EvidenceAnchor(type="dom", reference="e4"),),
        )
        with tempfile.TemporaryDirectory() as td:
            in_path = Path(td) / "baton-mobile.json"
            out_path = Path(td) / "baton-mobile-trimmed.json"
            in_path.write_text(json.dumps(baton), encoding="utf-8")
            summary = trim_baton_file(in_path, [f1, f2], out_path)
            self.assertEqual(summary["input_count"], 4)
            self.assertEqual(summary["output_count"], 2)
            written = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual([el["e_index"] for el in written["elements"]], ["e2", "e4"])


class TestBuildTrimSummary(unittest.TestCase):
    """Phase 5.1 — baton trim sidecar for downstream observability.

    The trimmed baton only carries kept elements. The summary sidecar exposes
    what was removed so the synthesizer and operators can explain absences
    without re-loading the full baton.
    """

    def _baton_with_roles(self) -> dict:
        return {
            "schema_version": 1,
            "engagement_id": "2026-04-27-aaaaaaaa",
            "device": "mobile",
            "url": "https://example.com",
            "captured_at": "2026-04-27T16:00:00.000Z",
            "viewport": {"width": 390, "height": 844, "dpr_requested": 3, "dpr_actual": 3},
            "capture_state": {"hydration": "post-hydration", "overlays_detected": [], "page_height_px": 5000},
            "elements": [
                {"e_index": "e0", "tag": "button", "role": "button",
                 "accessible_name": "Add to cart",
                 "rect": {"x": 0, "y": 100, "width": 200, "height": 40}},
                {"e_index": "e1", "tag": "img", "role": "image",
                 "accessible_name": "Product gallery image 1",
                 "rect": {"x": 0, "y": 300, "width": 390, "height": 390}},
                {"e_index": "e2", "tag": "img", "role": "image",
                 "accessible_name": "Product gallery image 2",
                 "rect": {"x": 0, "y": 700, "width": 390, "height": 390}},
                {"e_index": "e3", "tag": "button", "role": "button",
                 "accessible_name": "Select color",
                 "rect": {"x": 0, "y": 1200, "width": 100, "height": 40}},
                {"e_index": "e4", "tag": "nav", "role": "navigation",
                 "accessible_name": "Footer navigation",
                 "rect": {"x": 0, "y": 2000, "width": 390, "height": 200}},
            ],
            "sections": [],
            "page_head": {},
        }

    def test_summary_records_input_and_output_counts(self):
        from assembly.synth_input import build_trim_summary
        baton = self._baton_with_roles()
        summary = build_trim_summary(baton, {"e0", "e3"})
        self.assertEqual(summary["input_element_count"], 5)
        self.assertEqual(summary["output_element_count"], 2)
        self.assertAlmostEqual(summary["trim_ratio"], 0.4)

    def test_summary_lists_kept_e_indexes_sorted_numerically(self):
        from assembly.synth_input import build_trim_summary
        baton = self._baton_with_roles()
        summary = build_trim_summary(baton, {"e3", "e0", "e1"})
        # Numeric sort — "e10" should not come before "e2" lexicographically
        self.assertEqual(summary["kept_e_indexes"], ["e0", "e1", "e3"])

    def test_summary_records_removed_elements_with_identifying_fields(self):
        from assembly.synth_input import build_trim_summary
        baton = self._baton_with_roles()
        summary = build_trim_summary(baton, {"e0"})
        removed_indexes = [r["e_index"] for r in summary["removed"]]
        self.assertEqual(removed_indexes, ["e1", "e2", "e3", "e4"])
        # Each removed entry carries enough context to reference the element
        # by name without an e_index citation.
        nav_entry = next(r for r in summary["removed"] if r["e_index"] == "e4")
        self.assertEqual(nav_entry["tag"], "nav")
        self.assertEqual(nav_entry["role"], "navigation")
        self.assertEqual(nav_entry["accessible_name_truncated"], "Footer navigation")
        self.assertEqual(nav_entry["scroll_y"], 2000)

    def test_summary_groups_counts_by_role(self):
        from assembly.synth_input import build_trim_summary
        baton = self._baton_with_roles()
        summary = build_trim_summary(baton, {"e0", "e1"})
        # Kept: 1 button (e0), 1 image (e1)
        self.assertEqual(summary["counts_by_role"]["kept"], {"button": 1, "image": 1})
        # Removed: 1 image (e2), 1 button (e3), 1 navigation (e4)
        self.assertEqual(
            summary["counts_by_role"]["removed"],
            {"button": 1, "image": 1, "navigation": 1},
        )

    def test_summary_truncates_long_accessible_name(self):
        from assembly.synth_input import build_trim_summary
        baton = self._baton_with_roles()
        baton["elements"][0]["accessible_name"] = "A" * 200
        summary = build_trim_summary(baton, set())
        button_entry = next(r for r in summary["removed"] if r["e_index"] == "e0")
        self.assertLessEqual(len(button_entry["accessible_name_truncated"]), 80)
        self.assertTrue(button_entry["accessible_name_truncated"].endswith("..."))

    def test_summary_carries_engagement_id_and_device(self):
        from assembly.synth_input import build_trim_summary
        baton = self._baton_with_roles()
        summary = build_trim_summary(baton, {"e0"})
        self.assertEqual(summary["engagement_id"], baton["engagement_id"])
        self.assertEqual(summary["device"], baton["device"])

    def test_summary_handles_empty_baton(self):
        from assembly.synth_input import build_trim_summary
        baton = {"engagement_id": "x", "device": "desktop", "elements": []}
        summary = build_trim_summary(baton, set())
        self.assertEqual(summary["input_element_count"], 0)
        self.assertEqual(summary["output_element_count"], 0)
        self.assertEqual(summary["trim_ratio"], 1.0)  # divide-by-zero guard
        self.assertEqual(summary["removed"], [])

    def test_summary_is_deterministic(self):
        from assembly.synth_input import build_trim_summary
        baton = self._baton_with_roles()
        a = build_trim_summary(baton, {"e1", "e3"})
        b = build_trim_summary(baton, {"e1", "e3"})
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_trim_baton_file_writes_sidecar_when_summary_path_given(self):
        baton = self._baton_with_roles()
        f1 = _finding(local_index=1, baton_index="e0")
        with tempfile.TemporaryDirectory() as td:
            in_path = Path(td) / "baton-mobile.json"
            out_path = Path(td) / "baton-mobile-trimmed.json"
            summary_path = Path(td) / "baton-mobile-trimmed-summary.json"
            in_path.write_text(json.dumps(baton), encoding="utf-8")
            result = trim_baton_file(in_path, [f1], out_path, summary_path=summary_path)
            self.assertTrue(summary_path.exists())
            self.assertEqual(result["summary_path"], str(summary_path))
            sidecar = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(sidecar["input_element_count"], 5)
            self.assertEqual(sidecar["output_element_count"], 1)
            self.assertEqual(sidecar["kept_e_indexes"], ["e0"])
            self.assertIn("removed", sidecar)

    def test_trim_baton_file_skips_sidecar_when_path_omitted(self):
        # Legacy callers passing only 3 args must still work; no sidecar written.
        baton = self._baton_with_roles()
        f1 = _finding(local_index=1, baton_index="e0")
        with tempfile.TemporaryDirectory() as td:
            in_path = Path(td) / "baton-mobile.json"
            out_path = Path(td) / "baton-mobile-trimmed.json"
            in_path.write_text(json.dumps(baton), encoding="utf-8")
            result = trim_baton_file(in_path, [f1], out_path)
            self.assertNotIn("summary_path", result)
            # No stray summary file alongside
            self.assertFalse((Path(td) / "baton-mobile-trimmed-summary.json").exists())


class TestComputePhrasingSeeds(unittest.TestCase):
    def test_filters_to_scope_page(self):
        f_page = _finding(local_index=1, scope="page")
        f_device = _finding(local_index=2, scope="device")
        seeds = compute_phrasing_seeds([f_page, f_device])
        self.assertEqual(len(seeds), 1)
        self.assertEqual(seeds[0].f_ref, "pricing F-01")

    def test_orders_by_priority_then_tier_then_confidence(self):
        # All scope='page'; differing severity / tier / confidence
        f_low_silver = _finding(local_index=1, priority="LOW", tier="Silver", confidence=0.8)
        f_high_bronze = _finding(local_index=2, priority="HIGH", tier="Bronze", confidence=0.6)
        f_high_gold = _finding(local_index=3, priority="HIGH", tier="Gold", confidence=0.9)
        f_high_gold_lower_conf = _finding(local_index=4, priority="HIGH", tier="Gold", confidence=0.7)
        seeds = compute_phrasing_seeds(
            [f_low_silver, f_high_bronze, f_high_gold, f_high_gold_lower_conf]
        )
        ordered_local_ids = [int(s.f_ref.split("F-")[1]) for s in seeds]
        # Expected: HIGH+Gold+0.9 (idx 3), HIGH+Gold+0.7 (idx 4), HIGH+Bronze (idx 2), LOW (idx 1)
        self.assertEqual(ordered_local_ids, [3, 4, 2, 1])

    def test_seed_renders_markdown_block(self):
        f = _finding(
            local_index=1,
            title="No MSRP Anchor",
            observation="Bare $69.95 — no strikethrough.",
            recommendation="Add MSRP $89.95 strikethrough.",
            why_matters="Anchoring lifts perceived value.",
        )
        seeds = compute_phrasing_seeds([f])
        rendered = seeds[0].render_markdown()
        self.assertIn("### pricing F-01 - No MSRP Anchor", rendered)
        self.assertIn("**OBSERVATION:** Bare $69.95", rendered)
        self.assertIn("**RECOMMENDATION:** Add MSRP $89.95", rendered)
        self.assertIn("**Why this matters:** Anchoring lifts", rendered)

    def test_render_seeds_block_empty_when_no_page_findings(self):
        f = _finding(scope="device")
        seeds = compute_phrasing_seeds([f])
        block = render_phrasing_seeds_block(seeds)
        self.assertEqual(block, "")

    def test_render_seeds_block_concatenates_seeds(self):
        f1 = _finding(local_index=1, cluster="pricing", scope="page")
        f2 = _finding(local_index=2, cluster="visual-cta", scope="page", priority="HIGH")
        seeds = compute_phrasing_seeds([f1, f2])
        block = render_phrasing_seeds_block(seeds)
        self.assertIn("pricing F-01", block)
        self.assertIn("visual-cta F-02", block)
        # HIGH should sort before MEDIUM in the rendered block
        self.assertLess(block.index("visual-cta F-02"), block.index("pricing F-01"))

    def test_determinism(self):
        f1 = _finding(local_index=1, scope="page")
        f2 = _finding(local_index=2, cluster="visual-cta", scope="page")
        a = render_phrasing_seeds_block(compute_phrasing_seeds([f1, f2]))
        b = render_phrasing_seeds_block(compute_phrasing_seeds([f1, f2]))
        self.assertEqual(a, b)


class TestLevenshtein(unittest.TestCase):
    def test_zero_distance_for_identical(self):
        self.assertEqual(levenshtein_distance("hello", "hello"), 0)
        self.assertEqual(levenshtein_ratio("hello", "hello"), 0.0)

    def test_distance_for_disjoint(self):
        self.assertEqual(levenshtein_distance("abc", "xyz"), 3)
        self.assertEqual(levenshtein_ratio("abc", "xyz"), 1.0)

    def test_known_distances(self):
        self.assertEqual(levenshtein_distance("kitten", "sitting"), 3)
        self.assertEqual(levenshtein_distance("", "abc"), 3)
        self.assertEqual(levenshtein_distance("abc", ""), 3)

    def test_ratio_handles_empty_inputs(self):
        self.assertEqual(levenshtein_ratio("", ""), 0.0)

    def test_small_drift_under_threshold(self):
        a = "The price block renders $69.95 with no MSRP anchor."
        b = "The price block renders $69.95 with no MSRP anchor "  # extra space
        ratio = levenshtein_ratio(a, b)
        self.assertLess(ratio, SYNCHRONIZATION_THRESHOLD)


class TestExtractFindingProse(unittest.TestCase):
    AUDIT_MD = """# Audit — slingmods PDP (mobile)

## Findings by Cluster

### pricing F-01 - No MSRP Anchor on Price Block

**OBSERVATION:** Bare $69.95 — no strikethrough, no compare-at line.

**RECOMMENDATION:** Add MSRP $89.95 strikethrough above the live price.

**Why this matters:** Anchoring lifts perceived value 5-15% per Grewal et al.

### pricing F-02 - Affirm BNPL Absent at Price Block

**OBSERVATION:** Affirm logo in footer but not at price.

**RECOMMENDATION:** Add Affirm widget directly below the price line.

**Why this matters:** BNPL visibility lifts basket size 10% per Maesen 2025.

## Methodology Notes

Audit ran in single-shot mode.
"""

    def test_extracts_three_paragraphs(self):
        prose = extract_finding_prose(self.AUDIT_MD, "pricing F-01")
        self.assertIsNotNone(prose)
        obs, rec, why = prose
        self.assertIn("Bare $69.95", obs)
        self.assertIn("MSRP $89.95 strikethrough", rec)
        self.assertIn("Anchoring lifts", why)

    def test_returns_none_for_missing_finding(self):
        prose = extract_finding_prose(self.AUDIT_MD, "pricing F-99")
        self.assertIsNone(prose)

    def test_extracts_correct_finding_when_multiple_present(self):
        prose = extract_finding_prose(self.AUDIT_MD, "pricing F-02")
        self.assertIsNotNone(prose)
        obs, _, _ = prose
        self.assertIn("Affirm logo", obs)


class TestAssertSynchronizationInvariant(unittest.TestCase):
    DESKTOP = """### pricing F-01 - No MSRP Anchor

**OBSERVATION:** The price block renders $69.95 with no anchor.

**RECOMMENDATION:** Add MSRP $89.95 strikethrough above the live price.

**Why this matters:** Anchoring lifts perceived value.
"""

    MOBILE_IDENTICAL = DESKTOP

    MOBILE_SMALL_DRIFT = """### pricing F-01 - No MSRP Anchor

**OBSERVATION:** The price block renders $69.95 with no anchor.

**RECOMMENDATION:** Add MSRP $89.95 strikethrough above the live price.

**Why this matters:** Anchoring lifts perceived value.

"""  # trailing blank lines only - within tolerance

    MOBILE_LARGE_DRIFT = """### pricing F-01 - No MSRP Anchor

**OBSERVATION:** The mobile pricing block lacks a MSRP comparison element.

**RECOMMENDATION:** Insert a strikethrough field above the displayed price showing manufacturer suggested retail.

**Why this matters:** Cross-anchor framing increases willingness-to-pay measurably across the consideration spectrum.
"""  # paraphrased — significant drift

    def test_identical_documents_pass(self):
        report = assert_synchronization_invariant(
            self.DESKTOP, self.MOBILE_IDENTICAL, ["pricing F-01"]
        )
        self.assertTrue(report.ok)
        self.assertEqual(report.max_ratio, 0.0)
        self.assertEqual(len(report.per_finding), 1)
        self.assertEqual(report.per_finding[0][0], "pricing F-01")
        for ratio in report.per_finding[0][1:]:
            self.assertEqual(ratio, 0.0)

    def test_small_drift_under_threshold_passes(self):
        report = assert_synchronization_invariant(
            self.DESKTOP, self.MOBILE_SMALL_DRIFT, ["pricing F-01"]
        )
        self.assertTrue(report.ok)
        self.assertLess(report.max_ratio, SYNCHRONIZATION_THRESHOLD)

    def test_large_drift_fails(self):
        report = assert_synchronization_invariant(
            self.DESKTOP, self.MOBILE_LARGE_DRIFT, ["pricing F-01"]
        )
        self.assertFalse(report.ok)
        self.assertGreater(report.max_ratio, SYNCHRONIZATION_THRESHOLD)

    def test_missing_finding_marks_report_failed(self):
        report = assert_synchronization_invariant(
            self.DESKTOP,
            self.MOBILE_IDENTICAL,
            ["pricing F-01", "pricing F-99"],  # F-99 not in either doc
        )
        self.assertFalse(report.ok)
        self.assertIn("pricing F-99", report.missing)

    def test_empty_scope_page_refs_passes(self):
        report = assert_synchronization_invariant(self.DESKTOP, self.MOBILE_LARGE_DRIFT, [])
        self.assertTrue(report.ok)
        self.assertEqual(report.max_ratio, 0.0)
        self.assertEqual(report.per_finding, ())


class TestG18WhySliceTerminatorHardening(unittest.TestCase):
    """G18 (2026-05-27): the why-slice for the LAST finding in an audit
    document used to run to EOF and absorb any trailing per-device
    ``## Methodology Notes`` section, producing false-positive drift
    when only the trailing section differed.

    Both Run ``2026-05-27-af72a2ae`` and Run ``2026-05-27-52f53a53``
    lead-reflections independently flagged this. Post-fix: the slice
    terminates at the next markdown heading of any level (2-4 hashes),
    so a per-device methodology/appendix can't bleed into the last
    finding's why-slice.
    """

    DESKTOP_WITH_TRAILING_SECTION = """### ethics F-33 - Cookie Consent Banner

**OBSERVATION:** Banner renders Accept / Decline with equivalent prominence.

**RECOMMENDATION:** No change required for US targeting.

**Why this matters:** EU ePrivacy Art 5(3) does not apply to this US-only page.

## Methodology Notes

Desktop capture ran in single-shot mode at 1920x1080.
Acquisition completed in 4.2s.
"""

    # Identical finding prose; the trailing per-device methodology section
    # is DIFFERENT (this is the exact shape Run B's drift gate false-fired on).
    MOBILE_WITH_DIFFERENT_TRAILING_SECTION = """### ethics F-33 - Cookie Consent Banner

**OBSERVATION:** Banner renders Accept / Decline with equivalent prominence.

**RECOMMENDATION:** No change required for US targeting.

**Why this matters:** EU ePrivacy Art 5(3) does not apply to this US-only page.

## Methodology Notes

Mobile capture ran in single-shot mode at 390x844 @3x DPR.
Acquisition completed in 5.8s, one overlay dismissed (cookie-consent).
"""

    def test_last_finding_why_slice_stops_at_methodology_section(self):
        """The headline G18 case. Pre-fix: max_ratio is high because the
        per-device methodology bleeds into the why-slice. Post-fix: 0.0."""
        report = assert_synchronization_invariant(
            self.DESKTOP_WITH_TRAILING_SECTION,
            self.MOBILE_WITH_DIFFERENT_TRAILING_SECTION,
            ["ethics F-33"],
        )
        self.assertTrue(
            report.ok,
            f"G18: per-device methodology section must NOT bleed into the "
            f"last finding's why-slice. report={report}",
        )
        self.assertEqual(
            report.max_ratio,
            0.0,
            "G18: when the finding prose is byte-identical, max_ratio must be "
            "exactly 0.0 regardless of any trailing per-device section.",
        )

    def test_last_finding_extracts_only_finding_prose(self):
        """extract_finding_prose on the LAST finding must NOT include the
        trailing methodology section in any slice (obs/rec/why)."""
        prose = extract_finding_prose(
            self.DESKTOP_WITH_TRAILING_SECTION, "ethics F-33"
        )
        self.assertIsNotNone(prose)
        obs, rec, why = prose
        for label, slice_text in (("obs", obs), ("rec", rec), ("why", why)):
            self.assertNotIn(
                "Methodology",
                slice_text,
                f"G18: the {label} slice for the last finding must not "
                f"absorb the trailing `## Methodology Notes` section. "
                f"slice was: {slice_text!r}",
            )
            self.assertNotIn(
                "single-shot mode",
                slice_text,
                f"G18: methodology body text leaked into {label} slice",
            )

    def test_intermediate_section_heading_also_terminates_body(self):
        """Defensive: even if a `##` heading appears mid-document between
        two findings (uncommon but possible in operator-edited audits), the
        earlier finding's body slice terminates at that heading rather than
        running to the next finding.
        """
        doc = """### pricing F-01 - Price Anchor Missing

**OBSERVATION:** Bare price.

**RECOMMENDATION:** Add MSRP anchor.

**Why this matters:** Anchoring lifts perceived value.

## Inserted Operator Note

This section is unrelated to F-01.

### pricing F-02 - BNPL Missing

**OBSERVATION:** No BNPL widget.

**RECOMMENDATION:** Add Affirm.

**Why this matters:** BNPL lifts basket size.
"""
        prose = extract_finding_prose(doc, "pricing F-01")
        self.assertIsNotNone(prose)
        _obs, _rec, why = prose
        self.assertNotIn(
            "Inserted Operator Note",
            why,
            "G18: an intermediate `##` heading between findings must "
            "terminate the earlier finding's body slice.",
        )
        self.assertNotIn(
            "unrelated to F-01",
            why,
            "G18: body of an intermediate `##` section must not leak.",
        )


if __name__ == "__main__":
    unittest.main()
