"""Visual evidence quality gates (Phase 3 — 2026-05-18).

Tests for the four gates in ``scripts/assembly/visual_quality.py``:
- ``check_giant_exact_rectangles``
- ``check_proxy_overload``
- ``check_priority_path_needs_review``
- ``compute_visual_evidence_summary`` + ``render_summary_table``
- ``run_visual_quality_gates`` end-to-end against a review-state fixture
- ``run_all_canaries(include_visual_quality=True)`` integration

See ``docs/ecp/2026-05-18-report-accuracy-and-hotspot-remediation-plan.md``
Phase 3 acceptance criteria.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from assembly.canary_checks import run_all_canaries
from assembly.visual_quality import (
    DEFAULT_GIANT_HEIGHT_PCT,
    DEFAULT_GIANT_WIDTH_PCT,
    DEFAULT_PROXY_OVERLOAD_RATIO,
    check_giant_exact_rectangles,
    check_priority_path_needs_review,
    check_proxy_overload,
    compute_visual_evidence_summary,
    render_summary_table,
    run_visual_quality_gates,
)


def _marker(
    *,
    f_ref: str = "pricing F-01",
    type_: str = "exact_element",
    confidence: str = "high",
    w_pct: float = 30.0,
    h_pct: float = 20.0,
    slide: int = 0,
) -> dict:
    return {
        "f_ref": f_ref,
        "finding_index": int(f_ref.split("F-")[-1]),
        "slide": slide,
        "visual_evidence": {"type": type_, "confidence": confidence},
        "zone": {"left_pct": 10.0, "top_pct": 10.0, "w_pct": w_pct, "h_pct": h_pct},
    }


def _finding(
    *,
    f_ref: str = "pricing F-01",
    type_: str = "exact_element",
    confidence: str = "high",
    cluster: str = "pricing",
    ethics_state: str | None = None,
    verdict: str = "FAIL",
) -> dict:
    f = {
        "f_ref": f_ref,
        "cluster": cluster,
        "verdict": verdict,
        "visual_evidence": {"type": type_, "confidence": confidence},
    }
    if ethics_state is not None:
        f["ethics_state"] = ethics_state
    return f


# ---------------------------------------------------------------------------
# Gate 1 — giant exact rectangles
# ---------------------------------------------------------------------------


class TestGiantExactRectangles:
    def test_all_within_threshold_passes(self):
        markers = [
            _marker(f_ref="pricing F-01", w_pct=50, h_pct=30),
            _marker(f_ref="pricing F-02", w_pct=70, h_pct=40),
        ]
        r = check_giant_exact_rectangles(markers)
        assert r["passed"]
        assert r["detail"]["exact_count"] == 2
        assert r["detail"]["violation_count"] == 0

    def test_wide_rectangle_fails(self):
        markers = [_marker(f_ref="pricing F-01", w_pct=90, h_pct=20)]
        r = check_giant_exact_rectangles(markers)
        assert not r["passed"]
        assert r["detail"]["violations"][0]["f_ref"] == "pricing F-01"

    def test_tall_rectangle_fails(self):
        markers = [_marker(f_ref="pricing F-01", w_pct=30, h_pct=85)]
        r = check_giant_exact_rectangles(markers)
        assert not r["passed"]

    def test_proxy_with_giant_zone_is_skipped(self):
        # Proxy elements ARE allowed to be larger — dashed rect signals
        # "approximate." Gate only enforces against exact_element.
        markers = [_marker(f_ref="pricing F-01", type_="proxy_element", w_pct=95, h_pct=80)]
        r = check_giant_exact_rectangles(markers)
        assert r["passed"]
        assert r["detail"]["exact_count"] == 0

    def test_marker_without_zone_skipped(self):
        markers = [{
            "f_ref": "pricing F-01",
            "visual_evidence": {"type": "exact_element", "confidence": "high"},
            # No zone → point marker
        }]
        r = check_giant_exact_rectangles(markers)
        assert r["passed"]
        assert r["detail"]["exact_count"] == 0

    def test_legacy_marker_without_visual_evidence_skipped(self):
        markers = [{"f_ref": "pricing F-01", "zone": {"w_pct": 99, "h_pct": 99}}]
        r = check_giant_exact_rectangles(markers)
        assert r["passed"]

    def test_custom_thresholds_honored(self):
        # A 60% wide rectangle should pass default but fail at 50% threshold.
        markers = [_marker(w_pct=60, h_pct=30)]
        assert check_giant_exact_rectangles(markers)["passed"]
        assert not check_giant_exact_rectangles(markers, max_width_pct=50)["passed"]


# ---------------------------------------------------------------------------
# Gate 2 — proxy overload
# ---------------------------------------------------------------------------


class TestProxyOverload:
    def test_all_exact_passes(self):
        findings = [_finding(f_ref=f"p F-{i}") for i in range(5)]
        r = check_proxy_overload(findings)
        assert r["passed"]
        assert r["detail"]["non_exact_count"] == 0

    def test_some_proxy_under_threshold_passes(self):
        # 4 exact, 1 proxy = 20% non-exact, under 40% default
        findings = [
            _finding(f_ref=f"p F-{i}", type_="exact_element") for i in range(4)
        ] + [_finding(f_ref="p F-5", type_="proxy_element")]
        r = check_proxy_overload(findings)
        assert r["passed"]
        assert r["detail"]["ratio"] == 0.2

    def test_majority_non_exact_fails(self):
        # 1 exact, 4 non-exact = 80%
        findings = [_finding(f_ref="p F-1", type_="exact_element")] + [
            _finding(f_ref=f"p F-{i}", type_="generated_expected_zone") for i in range(2, 6)
        ]
        r = check_proxy_overload(findings)
        assert not r["passed"]
        assert r["detail"]["ratio"] == 0.8

    def test_empty_findings_passes(self):
        r = check_proxy_overload([])
        assert r["passed"]
        assert "skipped" in r["summary"]

    def test_legacy_findings_skipped(self):
        # No visual_evidence on any finding → all skipped, pass
        findings = [{"f_ref": "p F-1"}, {"f_ref": "p F-2"}]
        r = check_proxy_overload(findings)
        assert r["passed"]
        assert r["detail"]["typed_count"] == 0

    def test_by_type_breakdown_in_detail(self):
        findings = [
            _finding(f_ref="p F-1", type_="exact_element"),
            _finding(f_ref="p F-2", type_="proxy_element"),
            _finding(f_ref="p F-3", type_="generated_expected_zone"),
            _finding(f_ref="p F-4", type_="generated_expected_zone"),
        ]
        r = check_proxy_overload(findings)
        assert r["detail"]["by_type"] == {
            "exact_element": 1,
            "generated_expected_zone": 2,
            "proxy_element": 1,
        }


# ---------------------------------------------------------------------------
# Gate 3 — Priority Path / ethics shipping needs_review
# ---------------------------------------------------------------------------


class TestPriorityPathNeedsReview:
    def test_no_needs_review_passes(self):
        findings = [_finding(f_ref="p F-1", confidence="high")]
        r = check_priority_path_needs_review(
            findings, priority_path_refs=["p F-1"],
        )
        assert r["passed"]

    def test_priority_path_finding_needs_review_fails(self):
        findings = [_finding(f_ref="p F-1", confidence="needs_review")]
        r = check_priority_path_needs_review(
            findings, priority_path_refs=["p F-1"],
        )
        assert not r["passed"]
        assert r["detail"]["violations"][0]["f_ref"] == "p F-1"
        assert r["detail"]["violations"][0]["is_priority"]

    def test_actionable_ethics_needs_review_fails(self):
        findings = [
            _finding(
                f_ref="ethics F-02", cluster="ethics", verdict="FAIL",
                ethics_state="ADJACENT", confidence="needs_review",
            ),
        ]
        r = check_priority_path_needs_review(findings, priority_path_refs=[])
        assert not r["passed"]
        assert r["detail"]["violations"][0]["is_ethics_actionable"]

    def test_clear_ethics_needs_review_passes(self):
        # CLEAR ethics findings (verdict=PASS, ethics_state=CLEAR) don't
        # render in default mode — needs_review is fine.
        findings = [
            _finding(
                f_ref="ethics F-05", cluster="ethics", verdict="PASS",
                ethics_state="CLEAR", confidence="needs_review",
            ),
        ]
        r = check_priority_path_needs_review(findings, priority_path_refs=[])
        assert r["passed"]

    def test_non_priority_non_ethics_needs_review_passes(self):
        # Regular finding outside Priority Path with needs_review is OK —
        # gate only enforces against high-visibility surfaces.
        findings = [_finding(f_ref="p F-50", confidence="needs_review")]
        r = check_priority_path_needs_review(
            findings, priority_path_refs=["p F-1"],
        )
        assert r["passed"]


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------


class TestSummaryTable:
    def test_counts_by_type_and_confidence(self):
        findings = [
            _finding(f_ref="p F-1", type_="exact_element", confidence="high"),
            _finding(f_ref="p F-2", type_="exact_element", confidence="high"),
            _finding(f_ref="p F-3", type_="proxy_element", confidence="medium"),
            _finding(f_ref="p F-4", type_="generated_expected_zone", confidence="low"),
            _finding(f_ref="p F-5", type_="page_level", confidence="needs_review"),
        ]
        summary = compute_visual_evidence_summary(findings)
        assert summary["exact_element"]["high"] == 2
        assert summary["proxy_element"]["medium"] == 1
        assert summary["generated_expected_zone"]["low"] == 1
        assert summary["page_level"]["needs_review"] == 1
        assert summary["_total"] == {"high": 2, "medium": 1, "low": 1, "needs_review": 1}

    def test_render_summary_table_contains_all_types(self):
        findings = [_finding(f_ref="p F-1", confidence="high")]
        rendered = render_summary_table(compute_visual_evidence_summary(findings))
        assert "VISUAL EVIDENCE QUALITY" in rendered
        for type_name in (
            "exact_element", "proxy_element", "generated_expected_zone",
            "section_absence", "page_level", "TOTAL",
        ):
            assert type_name in rendered


# ---------------------------------------------------------------------------
# End-to-end against a review-state file
# ---------------------------------------------------------------------------


class TestRunVisualQualityGates:
    def _review_state(self, findings: list[dict], markers: list[dict]) -> dict:
        return {
            "review_state_schema_version": 1,
            "engagement_id": "2026-05-18-deadbeef",
            "device": "desktop",
            "findings": findings,
            "markers": markers,
        }

    def test_clean_run_all_pass(self):
        rs = self._review_state(
            findings=[_finding(f_ref="p F-1", confidence="high")],
            markers=[_marker(w_pct=30, h_pct=20)],
        )
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "review-state-desktop.json"
            p.write_text(json.dumps(rs), encoding="utf-8")
            r = run_visual_quality_gates(p)
            assert r["all_passed"]

    def test_giant_rect_fails_run(self):
        rs = self._review_state(
            findings=[_finding(f_ref="p F-1", confidence="high")],
            markers=[_marker(w_pct=95, h_pct=90)],  # giant
        )
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "review-state-desktop.json"
            p.write_text(json.dumps(rs), encoding="utf-8")
            r = run_visual_quality_gates(p)
            assert not r["all_passed"]
            # Specifically the giant gate fails
            fail_names = {res["name"] for res in r["results"] if not res["passed"]}
            assert "visual_evidence_giant_exact_rectangles" in fail_names


# ---------------------------------------------------------------------------
# Integration with run_all_canaries
# ---------------------------------------------------------------------------


class TestRealReviewStateMarkerShape:
    """Phase 3 hardening (2026-05-18) — regression tests that exercise the
    real review-state marker shape, not the synthetic ``zone`` fixture.

    The original Phase 3 tests passed because they hand-built markers with
    a nested ``zone`` dict. Real markers produced by
    ``scripts/assembly/review_state._marker_from_ai`` carry top-level
    ``x_pct/y_pct/w_pct/h_pct`` and (pre-fix) had no ``visual_evidence``
    at all. Codex caught this: against real review-state the gate reported
    "0 of 0 exact-element markers → PASS" (a false pass).
    """

    def _real_marker(
        self,
        *,
        f_ref: str = "pricing F-01",
        x_pct: float = 5.0,
        y_pct: float = 5.0,
        w_pct: float = 90.0,
        h_pct: float = 90.0,
        ve_type: str | None = "exact_element",
    ) -> dict:
        """Mirror the shape ``_marker_from_ai`` returns for a rect marker:
        top-level ``x_pct/y_pct/w_pct/h_pct``, no nested ``zone``."""
        m = {
            "marker_id": f"marker-{f_ref.replace(' ', '-').lower()}",
            "f_ref": f_ref,
            "slide_id": "desktop-0",
            "shape": "rect",
            "x_pct": x_pct,
            "y_pct": y_pct,
            "w_pct": w_pct,
            "h_pct": h_pct,
            "stroke": "#ff0000",
            "stroke_width": 3,
            "source": "ai_suggestion",
            "snapped_baton_index": "e0",
            "severity": "high",
        }
        if ve_type is not None:
            m["visual_evidence"] = {"type": ve_type, "confidence": "high"}
        return m

    def test_giant_gate_fires_on_real_review_state_marker_shape(self):
        """The exact regression Codex flagged: a giant exact_element marker
        in real review-state shape (top-level _pct fields, no nested
        ``zone``) must trip the gate. Pre-fix this returned 0 violations
        because the gate only looked at ``m.get("zone")``."""
        markers = [self._real_marker(w_pct=95, h_pct=92)]
        r = check_giant_exact_rectangles(markers)
        assert not r["passed"], (
            "Giant exact-element marker in real review-state shape should "
            "fail the gate. If this passes, check_giant_exact_rectangles "
            "is reading only nested zone dicts and ignoring top-level "
            "x_pct/y_pct/w_pct/h_pct (Codex 2026-05-18 review note 2)."
        )
        # Must actually report a violation, not skip silently
        assert r["detail"]["exact_count"] == 1
        assert r["detail"]["violation_count"] == 1

    def test_normal_real_review_state_marker_passes(self):
        """A small marker in the real shape passes (not just because the
        gate skipped it as unrecognized)."""
        markers = [self._real_marker(w_pct=20, h_pct=15)]
        r = check_giant_exact_rectangles(markers)
        assert r["passed"]
        # Critically: it was COUNTED as an exact-element marker, not skipped
        assert r["detail"]["exact_count"] == 1
        assert r["detail"]["violation_count"] == 0

    def test_marker_without_visual_evidence_skipped_not_counted(self):
        """Markers without visual_evidence (truly legacy) should not be
        counted in the exact_count. This distinguishes "legacy marker" from
        "marker we couldn't read shape of"."""
        markers = [self._real_marker(w_pct=95, h_pct=92, ve_type=None)]
        r = check_giant_exact_rectangles(markers)
        assert r["passed"]
        assert r["detail"]["exact_count"] == 0  # skipped — no visual_evidence

    def test_marker_from_ai_carries_visual_evidence(self):
        """Directly exercise ``_marker_from_ai`` to confirm the Phase 3-H.1
        fix wired visual_evidence onto the marker dict. This is the
        producer of real review-state markers."""
        from assembly.review_state import _marker_from_ai

        mapping = {
            "match_method": "e_index_lookup",
            "baton_element_index": 0,
            "visual_evidence": {"type": "exact_element", "confidence": "high"},
        }
        ai_marker = {"zone": {"left_pct": 10, "top_pct": 20, "w_pct": 30, "h_pct": 40}}
        marker = _marker_from_ai(
            "marker-test", "pricing F-01", "desktop-0",
            ai_marker, mapping, severity="high",
        )
        assert marker.get("visual_evidence") == {
            "type": "exact_element", "confidence": "high",
        }
        # And the shape is the real top-level form, not nested
        assert "x_pct" in marker and "w_pct" in marker
        assert "zone" not in marker

    def test_marker_from_ai_carries_visual_evidence_on_point_shape(self):
        """Point markers (no zone in ai_marker) also need visual_evidence
        threading so non-rect findings still emit Phase 2 CSS classes."""
        from assembly.review_state import _marker_from_ai

        mapping = {
            "match_method": "section_centroid",
            "baton_element_index": None,
            "visual_evidence": {"type": "section_absence", "confidence": "low"},
        }
        marker = _marker_from_ai(
            "marker-test", "pricing F-02", "desktop-1",
            None, mapping, severity="medium",
        )
        assert marker.get("visual_evidence") == {
            "type": "section_absence", "confidence": "low",
        }
        assert marker.get("shape") == "point"


class TestEthicsActionableFromReviewState:
    """Phase 3 hardening — ensure review-state findings carry ethics_state +
    verdict so check_priority_path_needs_review can identify ADJACENT/BLOCK
    ethics that AREN'T in Priority Path. Pre-fix this gate only caught
    ethics findings via the Priority Path branch."""

    def test_adjacent_ethics_with_needs_review_caught_without_priority_path(self):
        """An ADJACENT ethics finding with confidence=needs_review must
        fail the gate even when it's not in Priority Path."""
        findings = [{
            "f_ref": "ethics F-44",
            "cluster": "ethics",
            "ethics_state": "ADJACENT",
            "verdict": "FAIL",
            "visual_evidence": {"type": "page_level", "confidence": "needs_review"},
        }]
        r = check_priority_path_needs_review(findings, priority_path_refs=[])
        assert not r["passed"]
        assert r["detail"]["violations"][0]["is_ethics_actionable"]

    def test_block_ethics_with_needs_review_caught(self):
        findings = [{
            "f_ref": "ethics F-90",
            "cluster": "ethics",
            "ethics_state": "BLOCK",
            "verdict": "FAIL",
            "visual_evidence": {"type": "page_level", "confidence": "needs_review"},
        }]
        r = check_priority_path_needs_review(findings, priority_path_refs=[])
        assert not r["passed"]

    def test_clear_ethics_with_needs_review_still_passes(self):
        """CLEAR ethics findings don't render in default mode — their
        visual_evidence quality is informational only."""
        findings = [{
            "f_ref": "ethics F-05",
            "cluster": "ethics",
            "ethics_state": "CLEAR",
            "verdict": "PASS",
            "visual_evidence": {"type": "page_level", "confidence": "needs_review"},
        }]
        r = check_priority_path_needs_review(findings, priority_path_refs=[])
        assert r["passed"]


class TestBuildInitialReviewStateEndToEnd:
    """End-to-end regression test using the REAL ``build_initial_review_state``
    function against a real engagement folder. This is the test Codex
    asked for: it must catch the false-pass behavior in pre-Phase-3-hardening
    code by exercising the full review-state writer + gate pipeline.
    """

    FIXED_ENGAGEMENT = REPO_ROOT / "docs" / "ecp" / "2026-05-18-5ff7a91f-fixed"

    @pytest.fixture
    def real_review_state(self, tmp_path: Path) -> Path:
        """Copy the committed fixed-engagement folder into tmp and build
        review-state from it via the real writer. Returns the path to
        review-state-desktop.json."""
        import shutil
        from assembly.atomic_write import atomic_write_json
        from assembly.review_state import build_initial_review_state

        if not self.FIXED_ENGAGEMENT.exists():
            pytest.skip(
                f"Fixed engagement fixture not committed at {self.FIXED_ENGAGEMENT}; "
                "skipping end-to-end review-state regression test."
            )
        dst = tmp_path / self.FIXED_ENGAGEMENT.name
        shutil.copytree(self.FIXED_ENGAGEMENT, dst)
        state = build_initial_review_state(dst, "desktop")
        rs_path = dst / "review-state-desktop.json"
        atomic_write_json(rs_path, state)
        return rs_path

    def test_real_review_state_markers_carry_visual_evidence(
        self, real_review_state: Path,
    ) -> None:
        """Markers written by the real ``build_initial_review_state`` must
        carry ``visual_evidence`` (Phase 3-H.1 fix). Pre-fix this was 0.
        """
        state = json.loads(real_review_state.read_text(encoding="utf-8"))
        markers = state.get("markers") or []
        assert markers, "Real review-state should produce markers"
        with_ve = sum(1 for m in markers if m.get("visual_evidence"))
        assert with_ve == len(markers), (
            f"Only {with_ve}/{len(markers)} markers carry visual_evidence. "
            "_marker_from_ai must propagate mapping.visual_evidence onto "
            "every returned marker dict (Phase 3-H.1)."
        )

    def test_real_review_state_findings_preserve_ethics_state(
        self, real_review_state: Path,
    ) -> None:
        """Findings written by the real writer must preserve ``ethics_state``
        so check_priority_path_needs_review can identify ADJACENT/BLOCK
        ethics (Phase 3-H.4 fix)."""
        state = json.loads(real_review_state.read_text(encoding="utf-8"))
        findings = state.get("findings") or []
        ethics_findings = [
            f for f in findings if f.get("cluster") == "ethics"
        ]
        assert ethics_findings, (
            "Fixed engagement has 3 ADJACENT ethics findings; review-state "
            "should preserve them"
        )
        # At least one ethics finding must have the actionable ethics_state
        actionable = [
            f for f in ethics_findings
            if f.get("ethics_state") in {"BLOCK", "ADJACENT"}
        ]
        assert actionable, (
            "No ethics findings carry ethics_state in {BLOCK, ADJACENT}. "
            "build_initial_review_state must thread the source emission's "
            "ethics_state field into review-state findings (Phase 3-H.4)."
        )

    def test_giant_gate_against_real_review_state_does_not_false_pass(
        self, real_review_state: Path, tmp_path: Path,
    ) -> None:
        """The exact regression Codex flagged: run ``run_visual_quality_gates``
        against a REAL review-state with a synthesized giant rectangle, and
        confirm the gate catches it.

        Pre-fix Phase 3-H.2, ``check_giant_exact_rectangles`` looked only
        at ``m.get("zone")`` which doesn't exist on real markers. The gate
        reported "0 of 0 exact-element markers → PASS" regardless of how
        many giant rectangles were present.
        """
        # Mutate the review-state to add a giant exact rectangle as the
        # first marker. The Phase 3-H.1 fix means every marker has
        # visual_evidence; we just amplify its w_pct/h_pct to trip the
        # gate.
        state = json.loads(real_review_state.read_text(encoding="utf-8"))
        markers = state["markers"]
        # Pick the first non-point marker and balloon its size
        target = next(
            (m for m in markers if m.get("shape") == "rect"),
            None,
        )
        if target is None:
            pytest.skip("No rect markers in real review-state to mutate")
        target["w_pct"] = 95.0
        target["h_pct"] = 92.0
        target["visual_evidence"] = {"type": "exact_element", "confidence": "high"}
        # Persist mutation
        real_review_state.write_text(json.dumps(state), encoding="utf-8")

        result = run_visual_quality_gates(real_review_state)
        assert not result["all_passed"], (
            "Real review-state with a 95%×92% exact-element marker should "
            "fail the giant-rectangle gate. If this passes, "
            "check_giant_exact_rectangles is still reading only nested "
            "zone dicts and ignoring top-level x_pct/y_pct/w_pct/h_pct "
            "(Codex 2026-05-18 review note 2)."
        )
        giant = next(
            r for r in result["results"]
            if r["name"] == "visual_evidence_giant_exact_rectangles"
        )
        assert giant["detail"]["violation_count"] >= 1
        assert giant["detail"]["exact_count"] >= 1, (
            "Gate must COUNT real-shape markers as exact-element, not "
            "skip them as legacy."
        )


class TestCanaryIntegration:
    def test_run_all_canaries_default_runs_phase_3_when_review_state_absent(self):
        """Phase 3 hardening: include_visual_quality defaults to True. When
        no review-state files exist in the engagement dir, the visual
        quality block is present but per_device is empty and no new
        CanaryResult dicts append to results — so engagements that haven't
        reached the render stage degrade cleanly.

        Phase 6 (2026-05-18) added priority_path_count_parity → 4 baseline
        canaries instead of 3. G16 (2026-05-27) added clusters_represented
        as the fifth. G22+G24 (2026-05-28) added
        trace_counters_reconcile_with_artifacts as the sixth (skips with
        PASS on fixtures without audit-trace.log)."""
        eng = REPO_ROOT / "tests" / "fixtures" / "v2_engagement_with_adjacent_ethics"
        result = run_all_canaries(eng, audited_domain="example.test")
        assert len(result["results"]) == 6
        assert "visual_quality" in result  # Block present even when empty
        assert result["visual_quality"]["per_device"] == {}

    def test_run_all_canaries_explicit_false_suppresses_phase_3(self):
        """Backward compat opt-out: callers that explicitly disable Phase 3
        (e.g., v1 determinism snapshots) see no visual_quality block.

        Phase 6 (2026-05-18) — baseline grew to 4 canaries with
        priority_path_count_parity. G16 (2026-05-27) added
        clusters_represented as the fifth. G22+G24 (2026-05-28) added
        trace_counters_reconcile_with_artifacts as the sixth."""
        eng = REPO_ROOT / "tests" / "fixtures" / "v2_engagement_with_adjacent_ethics"
        result = run_all_canaries(eng, audited_domain="example.test", include_visual_quality=False)
        assert len(result["results"]) == 6
        assert "visual_quality" not in result

    def test_run_all_canaries_with_visual_quality_runs_when_review_state_present(self, tmp_path):
        """When review-state files are present and include_visual_quality=True,
        Phase 3 gates appear in results and the visual_quality block populates."""
        # Build a minimal engagement folder with a review-state JSON
        eng = tmp_path / "engagement"
        eng.mkdir()
        # Required for Phase I canaries to run (one of them reads ethics-findings)
        (eng / "ethics-findings.json").write_text(json.dumps({
            "schema_version": 1, "engagement_id": "2026-05-18-deadbeef",
            "cluster": "ethics", "device": "page",
            "specialist_model": {"family": "sonnet", "version": "4.6"},
            "started_at": "2026-05-18T00:00:00.000Z",
            "completed_at": "2026-05-18T00:00:01.000Z",
            "status": "complete", "findings": [],
        }), encoding="utf-8")
        # Empty audit-{device}.md so element_index_match_rate has something to read
        (eng / "audit-desktop.md").write_text("# audit", encoding="utf-8")
        (eng / "audit-mobile.md").write_text("# audit", encoding="utf-8")
        # Review state with one clean finding + one giant rect violation
        rs = {
            "review_state_schema_version": 1,
            "engagement_id": "2026-05-18-deadbeef",
            "device": "desktop",
            "findings": [
                _finding(f_ref="p F-1", confidence="high"),
            ],
            "markers": [
                _marker(w_pct=99, h_pct=99),  # giant — should fail
            ],
        }
        (eng / "review-state-desktop.json").write_text(json.dumps(rs), encoding="utf-8")

        result = run_all_canaries(eng, include_visual_quality=True)
        assert "visual_quality" in result
        assert "per_device" in result["visual_quality"]
        # Phase 3 gates added to results list (3 phase-I + 3 phase-III = 6)
        assert len(result["results"]) >= 6
        # The giant gate should fail
        names = [r["name"] for r in result["results"]]
        assert "visual_evidence_giant_exact_rectangles" in names
        giant_result = next(r for r in result["results"] if r["name"] == "visual_evidence_giant_exact_rectangles")
        assert not giant_result["passed"]
