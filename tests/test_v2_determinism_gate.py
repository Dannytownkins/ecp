"""v2 unit tests: assembly.determinism_gate (Phase K determinism-gate helpers).

Tests cover:
- Trace-assertion counter parsing (v2 + v1 alias counters + missing-counter
  graceful handling).
- Structural canary (4th canary): pass/fail combinations.
- Citations-validity check: missing source files, invalid sections,
  forgiving heading match.
- TARr@N: presence-agreement metric.
- TARa@N: paired stability metric (uses Phase J finding_stability internally).
- aggregate_runs: full N-run gate with synthetic perturbed runs.
- Sanity check against ``fixtures/slingmods-pdp/`` — using the fixture as
  both reference and run-1 should yield TARr=TARa=1.0.

Run:
    python -m unittest tests.test_v2_determinism_gate

Slow tier: ``TestAggregateAgainstSlingmodsFixture`` and the TARa tests load
the all-MiniLM-L6-v2 model the first time. Fast tier (the rest) skips
embeddings via ``include_embeddings=False`` where applicable.

Authored Phase K (2026-04-29). See:
- scripts/assembly/determinism_gate.py — module under test
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts"))

from assembly.determinism_gate import (  # noqa: E402
    _normalize_heading,
    aggregate_runs,
    check_citations_validity,
    check_structural_canary,
    compute_tar_a,
    compute_tar_r,
    parse_trace_assertions,
    validate_run,
)


SLINGMODS_FIXTURE = _REPO / "fixtures" / "slingmods-pdp"
AWDMODS_FIXTURE = _REPO / "fixtures" / "awdmods-homepage"
REFERENCES_DIR = _REPO / "references"


# ---------------------------------------------------------------------------
# Trace-assertion parsing
# ---------------------------------------------------------------------------


class TestParseTraceAssertions(unittest.TestCase):
    """Parse audit-trace.log header into structured counters."""

    def test_parses_slingmods_v2_header(self):
        result = parse_trace_assertions(SLINGMODS_FIXTURE / "audit-trace.log")
        self.assertEqual(result["pipeline"], "v2")
        self.assertIn("desktop", result["devices"])
        self.assertIn("mobile", result["devices"])

        c = result["counters"]
        self.assertEqual(c["expected_specialist_count"], 20)
        self.assertEqual(c["team_spawned_specialists"], 20)
        self.assertEqual(c["cluster_files_written"], 20)
        self.assertEqual(c["subagent_spawned_synthesizer"], 1)
        self.assertEqual(c["subagent_spawned_ethics"], 1)
        self.assertTrue(c["ethics_gate_executed"])

    def test_v1_alias_counter_normalization(self):
        with tempfile.TemporaryDirectory() as td:
            trace = Path(td) / "audit-trace.log"
            trace.write_text(
                """# ECP Audit Forensic Trace
# Engagement: test-engagement
# Pipeline: v1
# Devices: desktop
# ASSERTIONS:
#   tasks_created_total: 5
#   expected_auditor_count: 10
#   team_spawned_acquirers: 1
#   team_spawned_auditors: 10
#   cluster_files_written: 10
#   ethics_gate_executed: true
""",
                encoding="utf-8",
            )
            result = parse_trace_assertions(trace)
            c = result["counters"]
            # v1 names should fold into v2 canonical names.
            self.assertEqual(c.get("expected_specialist_count"), 10)
            self.assertEqual(c.get("team_spawned_specialists"), 10)
            self.assertEqual(c.get("subagent_spawned_acquirers"), 1)

    def test_missing_counters_default_to_absent(self):
        with tempfile.TemporaryDirectory() as td:
            trace = Path(td) / "audit-trace.log"
            trace.write_text(
                """# ECP Audit Forensic Trace
# Engagement: empty
# Pipeline: v2
""",
                encoding="utf-8",
            )
            result = parse_trace_assertions(trace)
            # Missing counters not present in the dict; check_structural_canary
            # treats absent as 0/false.
            self.assertNotIn("cluster_files_written", result["counters"])
            self.assertNotIn("ethics_gate_executed", result["counters"])

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            parse_trace_assertions(Path("/nonexistent/audit-trace.log"))

    def test_devices_parsed_as_list(self):
        result = parse_trace_assertions(SLINGMODS_FIXTURE / "audit-trace.log")
        self.assertEqual(sorted(result["devices"]), ["desktop", "mobile"])


# ---------------------------------------------------------------------------
# Structural canary (4th canary)
# ---------------------------------------------------------------------------


class TestStructuralCanary(unittest.TestCase):
    def test_slingmods_fixture_passes(self):
        result = check_structural_canary(
            SLINGMODS_FIXTURE / "audit-trace.log",
            expected_specialist_count=20,
        )
        self.assertTrue(result["passed"], result["summary"])
        self.assertEqual(result["detail"]["cluster_files_written"], 20)
        self.assertEqual(result["detail"]["expected_specialist_count"], 20)
        self.assertGreaterEqual(result["detail"]["subagent_spawned_synthesizer"], 1)
        self.assertGreaterEqual(result["detail"]["subagent_spawned_ethics"], 1)
        self.assertTrue(result["detail"]["ethics_gate_executed"])

    def test_uses_traces_own_expected_count_when_not_overridden(self):
        result = check_structural_canary(SLINGMODS_FIXTURE / "audit-trace.log")
        self.assertTrue(result["passed"])
        self.assertEqual(result["detail"]["expected_specialist_count"], 20)

    def test_fails_when_specialist_count_mismatches(self):
        with tempfile.TemporaryDirectory() as td:
            trace = Path(td) / "audit-trace.log"
            trace.write_text(
                """# ECP Audit Forensic Trace
# Pipeline: v2
# ASSERTIONS:
#   expected_specialist_count: 20
#   team_spawned_specialists: 15
#   cluster_files_written: 15
#   subagent_spawned_synthesizer: 1
#   subagent_spawned_ethics: 1
#   ethics_gate_executed: true
""",
                encoding="utf-8",
            )
            result = check_structural_canary(trace)
            self.assertFalse(result["passed"])
            self.assertTrue(any(
                "cluster_files_written=15" in f
                for f in result["detail"]["failures"]
            ))

    def test_fails_when_synthesizer_did_not_run(self):
        with tempfile.TemporaryDirectory() as td:
            trace = Path(td) / "audit-trace.log"
            trace.write_text(
                """# ECP Audit Forensic Trace
# Pipeline: v2
# ASSERTIONS:
#   expected_specialist_count: 20
#   cluster_files_written: 20
#   subagent_spawned_synthesizer: 0
#   subagent_spawned_ethics: 1
#   ethics_gate_executed: true
""",
                encoding="utf-8",
            )
            result = check_structural_canary(trace)
            self.assertFalse(result["passed"])
            self.assertTrue(any(
                "synthesizer never ran" in f
                for f in result["detail"]["failures"]
            ))

    def test_fails_when_ethics_did_not_run(self):
        with tempfile.TemporaryDirectory() as td:
            trace = Path(td) / "audit-trace.log"
            trace.write_text(
                """# ECP Audit Forensic Trace
# Pipeline: v2
# ASSERTIONS:
#   expected_specialist_count: 20
#   cluster_files_written: 20
#   subagent_spawned_synthesizer: 1
#   subagent_spawned_ethics: 0
#   ethics_gate_executed: false
""",
                encoding="utf-8",
            )
            result = check_structural_canary(trace)
            self.assertFalse(result["passed"])
            self.assertEqual(len(result["detail"]["failures"]), 2)

    def test_missing_trace_file_returns_soft_fail(self):
        result = check_structural_canary(Path("/nonexistent/audit-trace.log"))
        self.assertFalse(result["passed"])
        self.assertTrue(result["detail"].get("file_missing"))


# ---------------------------------------------------------------------------
# Citations validity
# ---------------------------------------------------------------------------


class TestCitationsValidity(unittest.TestCase):
    def test_valid_source_passes(self):
        # The slingmods fixture cites real reference files. Findings live
        # in the per-cluster + ethics emissions (NOT the synth emission —
        # see module docstring "Finding-data sourcing" for the reason).
        from assembly.determinism_gate import aggregate_findings_from_engagement
        findings = aggregate_findings_from_engagement(SLINGMODS_FIXTURE)
        self.assertGreater(
            len(findings), 50,
            "Expected slingmods fixture to have >50 raw findings across cluster + ethics",
        )
        result = check_citations_validity(findings, REFERENCES_DIR)
        # The canary's HARD failure mode is missing source files (real
        # fabrication). The slingmods fixture must have zero fabricated
        # sources — every cited reference must be a real file.
        self.assertTrue(
            result["passed"],
            f"Slingmods fixture has {len(result['detail']['missing_sources'])} "
            f"fabricated reference sources: {result['detail']['missing_sources'][:5]}",
        )
        self.assertEqual(result["detail"]["source_pass_rate"], 1.0)
        # Section pass rate is advisory; real specialists drift on heading
        # format. Operationally we expect >=85%. Below that is a v2.1 ticket
        # (specialist template should constrain section format), but it's
        # not gate-blocking.
        self.assertGreaterEqual(
            result["detail"]["section_pass_rate"], 0.80,
            f"Slingmods section_pass_rate dropped below 0.80 — investigate "
            f"specialist section drift",
        )

    def test_missing_source_fails(self):
        findings = [{
            "cluster": "pricing",
            "local_id": 1,
            "reference_citations": [
                {"source": "nonexistent-reference.md", "tier": "Silver"}
            ],
        }]
        result = check_citations_validity(findings, REFERENCES_DIR)
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["detail"]["missing_sources"]), 1)
        self.assertEqual(
            result["detail"]["missing_sources"][0]["source"],
            "nonexistent-reference.md",
        )

    def test_empty_source_fails(self):
        findings = [{
            "cluster": "pricing",
            "local_id": 1,
            "reference_citations": [
                {"source": "", "tier": "Silver"}
            ],
        }]
        result = check_citations_validity(findings, REFERENCES_DIR)
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["detail"]["missing_sources"]), 1)

    def test_section_omitted_passes_when_source_resolves(self):
        # Pick a real reference file; section omitted = no section check.
        findings = [{
            "cluster": "pricing",
            "local_id": 1,
            "reference_citations": [
                {"source": "charm-pricing.md", "tier": "Silver"}
            ],
        }]
        result = check_citations_validity(findings, REFERENCES_DIR)
        self.assertTrue(result["passed"])
        self.assertEqual(result["detail"]["total_citations"], 1)

    def test_invalid_section_recorded_as_advisory(self):
        # Invalid sections are SOFT failures — recorded in detail but
        # don't fail the gate. See test_invalid_section_does_not_block_gate.
        findings = [{
            "cluster": "pricing",
            "local_id": 1,
            "reference_citations": [
                {
                    "source": "charm-pricing.md",
                    "section": "this-heading-definitely-does-not-exist",
                    "tier": "Silver",
                }
            ],
        }]
        result = check_citations_validity(findings, REFERENCES_DIR)
        self.assertEqual(len(result["detail"]["invalid_sections"]), 1)

    def test_no_citations_passes(self):
        # PASS findings may legitimately omit reference_citations.
        findings = [{"cluster": "pricing", "local_id": 1, "reference_citations": []}]
        result = check_citations_validity(findings, REFERENCES_DIR)
        self.assertTrue(result["passed"])
        self.assertEqual(result["detail"]["total_citations"], 0)
        self.assertEqual(result["detail"]["source_pass_rate"], 1.0)
        self.assertEqual(result["detail"]["section_pass_rate"], 1.0)

    def test_invalid_section_does_not_block_gate(self):
        # Section-anchor drift is advisory, not a hard fail (see canary
        # docstring "Soft failures (advisory — formatting drift)").
        findings = [{
            "cluster": "pricing",
            "local_id": 1,
            "reference_citations": [
                {
                    "source": "charm-pricing.md",
                    "section": "definitely-not-a-real-heading",
                    "tier": "Silver",
                }
            ],
        }]
        result = check_citations_validity(findings, REFERENCES_DIR)
        # Source resolved (charm-pricing.md exists) → passed=True even
        # though the section anchor drift is recorded.
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["detail"]["invalid_sections"]), 1)
        self.assertEqual(result["detail"]["source_pass_rate"], 1.0)
        self.assertLess(result["detail"]["section_pass_rate"], 1.0)

    def test_missing_references_dir_fails(self):
        findings = [{"cluster": "pricing", "local_id": 1, "reference_citations": []}]
        result = check_citations_validity(findings, Path("/nonexistent/refs/"))
        self.assertFalse(result["passed"])
        self.assertTrue(result["detail"].get("references_dir_missing"))

    def test_normalize_heading_slug_match(self):
        # The forgiving match accepts slug-style and Title Case interchange.
        self.assertEqual(
            _normalize_heading("Regulatory Disclosure"),
            _normalize_heading("regulatory-disclosure"),
        )
        self.assertEqual(
            _normalize_heading("Finding 3: Above-fold CTAs"),
            _normalize_heading("finding-3-above-fold-ctas"),
        )


# ---------------------------------------------------------------------------
# TARr@N (presence agreement)
# ---------------------------------------------------------------------------


class TestTARr(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_engagement(self, name: str, refs: list[tuple[str, int]]) -> Path:
        """Create a synthetic engagement dir with a single cluster file.

        The cluster file's `findings` array carries every (cluster, local_id)
        ref the test wants to register — works because aggregate_findings
        flattens across all `cluster-*-{device}.json` files in the dir.
        """
        eng_dir = self.tmp / name
        eng_dir.mkdir()
        findings = [
            {
                "cluster": cluster,
                "local_id": local_id,
                "verdict": "FAIL",
                "title": f"finding {cluster} {local_id}",
                "surface": "test",
                "element": {"baton_index": "e1"},
                "severity": "MEDIUM",
                "scope": "device",
                "device": "desktop",
                "effort": {"change_type": "css", "change_scope": "single-file"},
                "evidence_anchors": [],
                "reference_citations": [],
                "observation": "obs",
                "recommendation": "rec",
                "why_this_matters": "matters because of x and y and z and so on",
                "evidence_tier": "Silver",
            }
            for (cluster, local_id) in refs
        ]
        # Use a synthetic cluster filename — aggregate_findings_from_engagement
        # reads all cluster-*-{device}.json files regardless of the cluster slug.
        path = eng_dir / "cluster-test-desktop.json"
        path.write_text(json.dumps({"findings": findings}), encoding="utf-8")
        return eng_dir

    def test_perfect_agreement_returns_one(self):
        # All 3 runs surface the same 5 f_refs.
        refs = [("pricing", 1), ("pricing", 2), ("trust-credibility", 1),
                ("ethics", 1), ("visual-cta", 3)]
        paths = [
            self._write_engagement(f"run-{i}.json", refs) for i in range(1, 4)
        ]
        result = compute_tar_r(paths)
        self.assertEqual(result["tar_r"], 1.0)
        self.assertEqual(result["intersection_size"], 5)
        self.assertEqual(result["union_size"], 5)

    def test_partial_agreement(self):
        # Run 1 has 4 refs; run 2 has 3 (one different); run 3 has 3 (matching run 1).
        # Union = 5; Intersection = 2 (the two refs all three share).
        run1 = [("pricing", 1), ("pricing", 2), ("trust-credibility", 1),
                ("ethics", 1)]
        run2 = [("pricing", 1), ("pricing", 2), ("visual-cta", 3)]  # drops trust+ethics; adds vcta
        run3 = [("pricing", 1), ("pricing", 2), ("trust-credibility", 1)]
        # Intersection: pricing F-01, pricing F-02 (2)
        # Union: pricing F-01, F-02, trust-credibility F-01, ethics F-01, visual-cta F-03 (5)
        paths = [
            self._write_engagement("a.json", run1),
            self._write_engagement("b.json", run2),
            self._write_engagement("c.json", run3),
        ]
        result = compute_tar_r(paths)
        self.assertEqual(result["intersection_size"], 2)
        self.assertEqual(result["union_size"], 5)
        self.assertAlmostEqual(result["tar_r"], 2/5, places=4)

    def test_zero_agreement_returns_zero(self):
        # Disjoint runs: no f_ref appears in all of them.
        run1 = [("pricing", 1)]
        run2 = [("trust-credibility", 1)]
        run3 = [("ethics", 1)]
        paths = [
            self._write_engagement("a.json", run1),
            self._write_engagement("b.json", run2),
            self._write_engagement("c.json", run3),
        ]
        result = compute_tar_r(paths)
        self.assertEqual(result["intersection_size"], 0)
        self.assertEqual(result["union_size"], 3)
        self.assertEqual(result["tar_r"], 0.0)

    def test_single_run_perfect_by_definition(self):
        run1 = [("pricing", 1), ("pricing", 2)]
        paths = [self._write_engagement("a.json", run1)]
        result = compute_tar_r(paths)
        # With 1 run, intersection = union, tar_r = 1.0
        self.assertEqual(result["tar_r"], 1.0)

    def test_empty_input_returns_zero(self):
        result = compute_tar_r([])
        self.assertEqual(result["tar_r"], 0.0)
        self.assertEqual(result["n_runs"], 0)

    def test_per_ref_presence_recorded(self):
        run1 = [("pricing", 1), ("pricing", 2)]
        run2 = [("pricing", 1)]
        paths = [
            self._write_engagement("a.json", run1),
            self._write_engagement("b.json", run2),
        ]
        result = compute_tar_r(paths)
        self.assertEqual(result["per_ref_presence"]["pricing F-01"]["present_in_runs"], 2)
        self.assertEqual(result["per_ref_presence"]["pricing F-02"]["present_in_runs"], 1)


# ---------------------------------------------------------------------------
# TARa@N (semantic agreement via Phase J stability)
# ---------------------------------------------------------------------------


class TestTARa(unittest.TestCase):
    """Tests for compute_tar_a — uses --no-embeddings via include_embeddings=False
    to keep tests fast (no MiniLM model load)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_engagement(self, name: str, findings: list[dict]) -> Path:
        """Write findings into a synthetic cluster emission file in a new dir.

        compute_tar_a aggregates findings from cluster + ethics emissions
        in the engagement dir (per the Phase K finding-data sourcing rule),
        so we write to ``cluster-test-desktop.json`` instead of the synth
        emission shape.
        """
        eng_dir = self.tmp / name
        eng_dir.mkdir()
        path = eng_dir / "cluster-test-desktop.json"
        path.write_text(json.dumps({"findings": findings}), encoding="utf-8")
        return eng_dir

    def _make_finding(self, cluster: str, local_id: int, **overrides) -> dict:
        f = {
            "cluster": cluster,
            "local_id": local_id,
            "verdict": "FAIL",
            "title": f"Finding for {cluster} number {local_id}",
            "surface": "primary-cta",
            "element": {"baton_index": f"e{local_id + 10}"},
            "severity": "MEDIUM",
            "scope": "device",
            "device": "desktop",
            "effort": {"change_type": "css", "change_scope": "single-file"},
            "evidence_anchors": [],
            "reference_citations": [],
            "observation": "Observation prose " * 5,
            "recommendation": "Recommendation prose " * 5,
            "why_this_matters": "It matters because here is a long explanation",
            "evidence_tier": "Silver",
        }
        f.update(overrides)
        return f

    def test_identical_runs_pass_stability(self):
        findings = [self._make_finding("pricing", 1), self._make_finding("pricing", 2)]
        ref = self._write_engagement("ref", findings)
        cand = self._write_engagement("cand", deepcopy(findings))
        result = compute_tar_a(ref, [cand], include_embeddings=False)
        self.assertEqual(result["paired_total"], 2)
        self.assertEqual(result["paired_passed"], 2)
        self.assertEqual(result["tar_a"], 1.0)

    def test_severity_drift_outside_tolerance_fails(self):
        ref_findings = [self._make_finding("pricing", 1, severity="HIGH")]
        cand_findings = [self._make_finding("pricing", 1, severity="LOW")]
        ref = self._write_engagement("ref", ref_findings)
        cand = self._write_engagement("cand", cand_findings)
        # severity_distance(HIGH=3, LOW=1) = 2 — fails default max_severity_distance=1.
        result = compute_tar_a(ref, [cand], include_embeddings=False)
        self.assertEqual(result["paired_total"], 1)
        self.assertEqual(result["paired_passed"], 0)
        self.assertLess(result["tar_a"], 0.5)

    def test_baton_index_drift_fails(self):
        ref_findings = [self._make_finding("pricing", 1)]  # baton_index=e11
        cand_findings = [self._make_finding("pricing", 1)]
        cand_findings[0]["element"]["baton_index"] = "e99"
        ref = self._write_engagement("ref", ref_findings)
        cand = self._write_engagement("cand", cand_findings)
        result = compute_tar_a(ref, [cand], include_embeddings=False)
        self.assertEqual(result["paired_passed"], 0)

    def test_no_candidates_returns_one(self):
        findings = [self._make_finding("pricing", 1)]
        ref = self._write_engagement("ref", findings)
        result = compute_tar_a(ref, [], include_embeddings=False)
        # No candidates = vacuously perfect (no comparison made).
        self.assertEqual(result["tar_a"], 1.0)
        self.assertEqual(result["paired_total"], 0)


# ---------------------------------------------------------------------------
# validate_run — full per-run check against slingmods fixture
# ---------------------------------------------------------------------------


class TestValidateRun(unittest.TestCase):
    def test_slingmods_fixture_validates_clean(self):
        report = validate_run(
            SLINGMODS_FIXTURE,
            audited_domain="slingmods.com",
            references_dir=REFERENCES_DIR,
            expected_specialist_count=20,
        )
        self.assertTrue(
            report["all_passed"],
            f"Slingmods fixture failed validate_run: "
            f"canaries={[(c['name'], c['passed']) for c in report['canaries']]} "
            f"citations_passed={report['citations']['passed']}",
        )
        # Phase 6 (2026-05-18) added priority_path_count_parity →
        # 5 canaries: 4 substantive + 1 structural. G16 (2026-05-27)
        # added clusters_represented → 6: 5 substantive + 1 structural.
        # G22+G24 (2026-05-28) added trace_counters_reconcile_with_artifacts
        # → 7: 6 substantive + 1 structural.
        self.assertEqual(len(report["canaries"]), 7)
        canary_names = [c["name"] for c in report["canaries"]]
        self.assertIn("ethics_findings_have_source_urls", canary_names)
        self.assertIn("element_index_match_rate", canary_names)
        self.assertIn("cross_device_ethics_diff", canary_names)
        self.assertIn("priority_path_count_parity", canary_names)
        self.assertIn("clusters_represented", canary_names)
        self.assertIn("trace_counters_reconcile_with_artifacts", canary_names)
        self.assertIn("structural_assertions", canary_names)


# ---------------------------------------------------------------------------
# aggregate_runs — N-run gate end-to-end
# ---------------------------------------------------------------------------


class TestAggregateRuns(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_rejects_single_run(self):
        run1 = self.tmp / "run-1"
        run1.mkdir()
        result = aggregate_runs(
            [run1],
            audited_domain="example.com",
            references_dir=REFERENCES_DIR,
        )
        self.assertFalse(result["gate_passed"])
        self.assertTrue(any(
            "need >= 2 runs" in v for v in result["gate_violations"]
        ))

    def test_invalid_reference_run_raises(self):
        run1 = self.tmp / "run-1"
        run1.mkdir()
        run2 = self.tmp / "run-2"
        run2.mkdir()
        with self.assertRaises(ValueError):
            aggregate_runs(
                [run1, run2],
                audited_domain="example.com",
                references_dir=REFERENCES_DIR,
                reference_run=99,
            )

    def test_dryrun_replicate_fixture_passes_gate(self):
        """Smoke-test the gate against 3 byte-identical replicas of the
        slingmods fixture. Should give TARr=TARa=1.0 and gate pass."""
        n_runs = 3
        run_dirs: list[Path] = []
        for i in range(1, n_runs + 1):
            run_dir = self.tmp / f"run-{i:02d}"
            shutil.copytree(SLINGMODS_FIXTURE, run_dir)
            run_dirs.append(run_dir)

        result = aggregate_runs(
            run_dirs,
            audited_domain="slingmods.com",
            references_dir=REFERENCES_DIR,
            expected_specialist_count=20,
            include_embeddings=False,
        )
        self.assertEqual(
            result["runs_passing_canaries"], n_runs,
            f"Some runs failed canaries: {result['runs_failing_canaries']}",
        )
        self.assertEqual(result["tar_r"], 1.0)
        self.assertEqual(result["tar_a"], 1.0)
        self.assertEqual(result["paired_findings_failed"]
                         if "paired_findings_failed" in result
                         else result["tar_a_detail"]["paired_failed"], 0)
        self.assertTrue(
            result["gate_passed"],
            f"Gate failed unexpectedly: {result['gate_violations']}",
        )

    def test_perturbed_run_below_threshold_fails_gate(self):
        """If we perturb one run's emissions to drift severity dramatically,
        TARa drops below 0.9 and the gate fails."""
        n_runs = 3
        run_dirs: list[Path] = []
        for i in range(1, n_runs + 1):
            run_dir = self.tmp / f"run-{i:02d}"
            shutil.copytree(SLINGMODS_FIXTURE, run_dir)
            run_dirs.append(run_dir)

        # Perturb run-2 and run-3: flip every cluster + ethics finding's
        # baton_index to 'absent' (catastrophic structural drift — every
        # paired finding fails the byte-equal element.baton_index check).
        # Routes through the cluster-*-{device}.json + ethics-findings.json
        # files since that's where TARa sources findings (see module
        # docstring "Finding-data sourcing").
        for run in run_dirs[1:]:
            for emission_path in list(run.glob("cluster-*-desktop.json")) \
                    + list(run.glob("cluster-*-mobile.json")) \
                    + [run / "ethics-findings.json"]:
                if not emission_path.exists():
                    continue
                if emission_path.name.startswith("cluster-context-"):
                    continue
                data = json.loads(emission_path.read_text(encoding="utf-8"))
                for f in data.get("findings", []):
                    if isinstance(f.get("element"), dict):
                        f["element"]["baton_index"] = "absent"
                emission_path.write_text(json.dumps(data), encoding="utf-8")

        result = aggregate_runs(
            run_dirs,
            audited_domain="slingmods.com",
            references_dir=REFERENCES_DIR,
            expected_specialist_count=20,
            include_embeddings=False,
        )
        # TARa should plummet; gate should fail on stability.
        self.assertLess(result["tar_a"], 0.9)
        self.assertFalse(result["gate_passed"])
        self.assertTrue(any(
            "TARa@" in v for v in result["gate_violations"]
        ))


# ---------------------------------------------------------------------------
# Awdmods fixture sanity (the secondary fixture should also validate)
# ---------------------------------------------------------------------------


@unittest.skipUnless(
    AWDMODS_FIXTURE.is_dir(),
    "awdmods fixture absent",
)
class TestAwdmodsFixtureSanity(unittest.TestCase):
    def test_awdmods_trace_parses(self):
        result = parse_trace_assertions(AWDMODS_FIXTURE / "audit-trace.log")
        self.assertEqual(result["pipeline"], "v2")
        self.assertGreater(
            result["counters"].get("expected_specialist_count", 0), 0
        )

    def test_awdmods_structural_canary(self):
        # The awdmods fixture is a valid v2 engagement; structural counters
        # must satisfy the contract regardless of the substantive
        # element_index_match_rate (which is fixture-accepted soft FAIL per
        # OC#5).
        result = check_structural_canary(AWDMODS_FIXTURE / "audit-trace.log")
        self.assertTrue(
            result["passed"],
            f"awdmods structural canary unexpectedly failed: "
            f"{result['detail']['failures']}",
        )


if __name__ == "__main__":
    unittest.main()
