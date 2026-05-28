"""G22+G24 regression: trace-counter / artifact reconciliation canary.

The ``contracts/dispatch-contract.md`` rule says the lead MUST increment
the relevant counter in ``audit-trace.log`` after every successful
dispatch. The structural-assertion self-check in
``contracts/trace-assertion-canary.md`` is supposed to surface
violations at audit completion. Engagement
``docs/ecp/2026-05-28-e4050c0e`` proved the gate was non-functional:
all four spawn counters read 0 while 12 specialist emissions + 1
ethics + 1 synth + 2 acquirers were observably on disk, and the lead
still wrote a (premature) reflection without the structural check
firing.

G24's ``check_trace_counters_reconcile_with_artifacts`` closes the
loop by walking the filesystem and asserting
``counter >= observed_artifact_count`` per role. G22 (the
trace-discipline rule existed but wasn't enforced) is effectively
addressed by G24's enforcement.

unittest-style for ``python -m unittest discover`` runner compatibility.

Run:
    python -m unittest tests.test_g24_trace_counters_reconcile
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
    check_trace_counters_reconcile_with_artifacts,
)


def _meta(clusters: list[str], devices: list[str]) -> dict:
    return {
        "id": "test-engagement",
        "page": {"url": "https://example.com", "type": "product"},
        "platform": "test",
        "source_mode": "url-dual",
        "devices_requested": devices,
        "devices_scanned": devices,
        "clusters_used": clusters,
        "scope": "comprehensive",
        "schema_version": 3,
        "type": "audit",
    }


def _trace(counters: dict[str, int], header_prefix: str = "") -> str:
    """Render an audit-trace.log style text body. Each counter renders as
    ``<key>: <int>`` on its own line; ``header_prefix`` lets tests stick
    a free-prose preamble in front to confirm parser tolerance."""
    body_lines = [f"{name}: {value}" for name, value in counters.items()]
    return header_prefix + "\n".join(body_lines) + "\n"


class TestTraceCountersReconcileCanary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.eng = Path(self.tmp.name) / "engagement"
        self.eng.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _write_meta(self, clusters: list[str], devices: list[str]):
        (self.eng / "meta.json").write_text(
            json.dumps(_meta(clusters, devices)), encoding="utf-8"
        )

    def _write_trace(self, counters: dict[str, int], header_prefix: str = ""):
        (self.eng / "audit-trace.log").write_text(
            _trace(counters, header_prefix), encoding="utf-8"
        )

    def _touch_cluster_emission(self, cluster: str, device: str):
        # Write a minimum-non-empty file; the canary only checks
        # presence + size > 0, not schema validity.
        (self.eng / f"cluster-{cluster}-{device}.json").write_text(
            json.dumps({"cluster": cluster, "device": device}),
            encoding="utf-8",
        )

    def _touch_baton(self, device: str):
        name = "baton.json" if device == "desktop" else "baton-mobile.json"
        (self.eng / name).write_text("{}", encoding="utf-8")

    def _touch_ethics(self):
        (self.eng / "ethics-findings.json").write_text("{}", encoding="utf-8")

    def _touch_synth(self):
        (self.eng / "synthesizer-emission-v1.json").write_text("{}", encoding="utf-8")

    # ------------------------------------------------------------------
    # Clean-run path
    # ------------------------------------------------------------------

    def test_clean_run_with_aligned_counters_passes(self):
        self._write_meta(["pricing", "visual-cta"], ["desktop", "mobile"])
        # 4 specialist emissions on disk
        for cluster in ("pricing", "visual-cta"):
            for device in ("desktop", "mobile"):
                self._touch_cluster_emission(cluster, device)
        for device in ("desktop", "mobile"):
            self._touch_baton(device)
        self._touch_ethics()
        self._touch_synth()
        self._write_trace({
            "subagent_spawned_acquirers": 2,
            "team_spawned_specialists": 4,
            "subagent_spawned_ethics": 1,
            "subagent_spawned_synthesizer": 1,
            "cluster_files_written": 4,
        })

        result = check_trace_counters_reconcile_with_artifacts(self.eng)
        self.assertTrue(
            result["passed"],
            f"Aligned trace + artifacts should PASS. summary={result['summary']!r}",
        )
        self.assertEqual(result["detail"]["violations"], [])

    def test_counter_over_count_still_passes(self):
        """Counter > observed (e.g., lead recorded a spawn whose emission
        later failed to land) is NOT a §0 violation — the lead's record
        of dispatches is at least as large as reality. The canary only
        fires when reality EXCEEDS the recorded counter (the actual G22
        case from docs/ecp/2026-05-28-e4050c0e)."""
        self._write_meta(["pricing"], ["desktop"])
        self._touch_cluster_emission("pricing", "desktop")
        self._touch_baton("desktop")
        self._touch_ethics()
        self._touch_synth()
        self._write_trace({
            "subagent_spawned_acquirers": 5,  # over-counted vs 1 observed
            "team_spawned_specialists": 12,   # over-counted vs 1 observed
            "subagent_spawned_ethics": 1,
            "subagent_spawned_synthesizer": 1,
            "cluster_files_written": 12,
        })
        result = check_trace_counters_reconcile_with_artifacts(self.eng)
        self.assertTrue(result["passed"])

    def test_v1_counter_alias_accepted_for_specialists(self):
        """contracts/dispatch-contract.md §"Backwards compatibility":
        v1 audits use team_spawned_auditors; v2 uses team_spawned_specialists.
        The canary accepts either as evidence the specialist role ran."""
        self._write_meta(["pricing"], ["desktop"])
        self._touch_cluster_emission("pricing", "desktop")
        self._touch_baton("desktop")
        self._touch_ethics()
        self._touch_synth()
        self._write_trace({
            "team_spawned_acquirers": 1,    # v1 acquirer counter name
            "team_spawned_auditors": 1,     # v1 specialist counter name
            "subagent_spawned_ethics": 1,
            "subagent_spawned_synthesizer": 1,
            "cluster_files_written": 1,
        })
        result = check_trace_counters_reconcile_with_artifacts(self.eng)
        self.assertTrue(
            result["passed"],
            f"v1 counter aliases must reconcile. summary={result['summary']!r}",
        )

    # ------------------------------------------------------------------
    # Fail-loud paths — the actual G22 failure mode
    # ------------------------------------------------------------------

    def test_g22_reproducer_zero_counters_against_full_artifacts(self):
        """docs/ecp/2026-05-28-e4050c0e: all counters at 0 but 12
        specialist emissions + 1 ethics + 1 synth + 2 acquirers on
        disk. Pre-G24 this slid past every other canary; post-G24 it
        must FAIL the canary loudly with each violating role named."""
        self._write_meta(
            [
                "visual-cta", "trust-credibility", "pricing",
                "product-media", "content-seo", "performance-ux",
            ],
            ["desktop", "mobile"],
        )
        for cluster in (
            "visual-cta", "trust-credibility", "pricing",
            "product-media", "content-seo", "performance-ux",
        ):
            for device in ("desktop", "mobile"):
                self._touch_cluster_emission(cluster, device)
        for device in ("desktop", "mobile"):
            self._touch_baton(device)
        self._touch_ethics()
        self._touch_synth()

        # The 2026-05-28-e4050c0e trace shape — counters all 0.
        self._write_trace(
            {
                "subagent_spawned_acquirers": 0,
                "team_spawned_specialists": 0,
                "subagent_spawned_ethics": 0,
                "subagent_spawned_synthesizer": 0,
            },
            header_prefix="# Counters\n",
        )

        result = check_trace_counters_reconcile_with_artifacts(self.eng)
        self.assertFalse(
            result["passed"],
            "G22 reproducer: all-zero counters against full artifacts must FAIL.",
        )
        # Summary should name every under-counted role so the operator
        # has a single line to act on.
        for role in ("acquirers", "specialists", "ethics", "synthesizer"):
            self.assertIn(
                role,
                result["summary"],
                f"Summary must name violating role {role!r}: {result['summary']!r}",
            )
        # Per-role detail records the gap.
        violations = {v["role"] for v in result["detail"]["roles"] if not v["reconciled"]}
        self.assertEqual(
            violations,
            {"acquirers", "specialists", "ethics", "synthesizer", "cluster_files_written"},
        )

    def test_partial_violation_specific_role_named(self):
        """When one role under-counts and others reconcile, only the
        offender shows up in the violations list — granularity matters
        for the operator's response."""
        self._write_meta(["pricing"], ["desktop"])
        self._touch_cluster_emission("pricing", "desktop")
        self._touch_baton("desktop")
        self._touch_ethics()
        self._touch_synth()
        self._write_trace({
            "subagent_spawned_acquirers": 1,
            "team_spawned_specialists": 0,   # under-counted vs 1 observed
            "subagent_spawned_ethics": 1,
            "subagent_spawned_synthesizer": 1,
            "cluster_files_written": 1,
        })

        result = check_trace_counters_reconcile_with_artifacts(self.eng)
        self.assertFalse(result["passed"])
        violation_roles = {
            v["role"] for v in result["detail"]["roles"] if not v["reconciled"]
        }
        self.assertEqual(violation_roles, {"specialists"})

    # ------------------------------------------------------------------
    # Skip-safe paths — test fixtures + pre-trace-stage engagements
    # ------------------------------------------------------------------

    def test_missing_trace_skips_with_pass(self):
        """Pre-trace-stage engagement (test fixture or aborted-before-trace
        run) skips cleanly so the canary doesn't false-positive on
        partial setups."""
        self._write_meta(["pricing"], ["desktop"])
        # No audit-trace.log written.

        result = check_trace_counters_reconcile_with_artifacts(self.eng)
        self.assertTrue(result["passed"])
        self.assertIn("skipped", result["summary"])

    def test_missing_meta_skips_with_pass(self):
        self._write_trace({"team_spawned_specialists": 0})
        # No meta.json.

        result = check_trace_counters_reconcile_with_artifacts(self.eng)
        self.assertTrue(result["passed"])
        self.assertIn("skipped", result["summary"])

    def test_trace_parser_tolerates_prose_and_event_lines(self):
        """The trace mixes counters, event-log lines, and prose. The
        parser only matches well-formed ``key: <int>`` lines and ignores
        the rest."""
        self._write_meta(["pricing"], ["desktop"])
        self._touch_cluster_emission("pricing", "desktop")
        self._touch_baton("desktop")
        trace_text = (
            "ECP v2 audit trace\n"
            "engagement_id: 2026-05-28-test\n"  # NOT a counter (string value)
            "url: https://example.com\n"
            "\n"
            "# Counters\n"
            "team_spawned_specialists: 1\n"
            "subagent_spawned_acquirers: 1\n"
            "cluster_files_written: 1\n"
            "\n"
            "[event] 2026-05-28T01:00:00Z dispatch complete\n"
        )
        (self.eng / "audit-trace.log").write_text(trace_text, encoding="utf-8")

        result = check_trace_counters_reconcile_with_artifacts(self.eng)
        # No ethics or synth present → those roles reconcile at 0/0.
        self.assertTrue(result["passed"], result["summary"])


if __name__ == "__main__":
    unittest.main()
