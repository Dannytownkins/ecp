"""Regression test for the lead_prep canonical-frefs manifest bug.

Pre-fix, `lead_prep.build_canonical_frefs` re-derived the manifest from cluster
emissions only — it never loaded ethics-findings.json and never ran
deduplicate_v2().all_actionable(). So the manifest handed to the synthesizer
disagreed with the renderer's allowlist (missing ethics refs, no cross-device
dedup), and the synthesizer emitted out-of-allowlist f_refs.

Fix: build_canonical_frefs now calls the renderer's own
scripts/report/v2_loader.build_canonical_view. This test pins that the manifest
== the renderer allowlist AND includes ethics findings.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import lead_prep  # noqa: E402
from report.v2_loader import (  # noqa: E402
    build_canonical_view,
    _engagement_cluster_emission_paths,
    _engagement_ethics_findings_path,
)

FIXTURE = ROOT / "tests" / "fixtures" / "v2_engagement_with_adjacent_ethics"


class TestCanonicalFrefsParity(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp())
        self.eng = self._tmp / "eng"
        shutil.copytree(FIXTURE, self.eng)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_manifest_equals_renderer_allowlist_and_includes_ethics(self):
        rc = lead_prep.build_canonical_frefs(self.eng)
        self.assertEqual(rc, 0, "build_canonical_frefs should succeed on the fixture")

        manifest = json.loads(
            (self.eng / "canonical-f-refs-manifest.json").read_text(encoding="utf-8")
        )
        manifest_refs = {e["f_ref"] for e in manifest["entries"]}
        self.assertTrue(manifest_refs, "manifest must not be empty")

        # The renderer's true allowlist, computed independently from the same inputs.
        by_ref, _aliases = build_canonical_view(
            _engagement_cluster_emission_paths(self.eng),
            _engagement_ethics_findings_path(self.eng),
        )
        self.assertEqual(
            manifest_refs,
            set(by_ref.keys()),
            "lead_prep manifest must equal the renderer's canonical allowlist (no split-brain)",
        )

        # The specific regression: ethics findings must be in the manifest.
        # Pre-fix they were dropped because ethics-findings.json was never loaded.
        self.assertTrue(
            any(r.startswith("ethics ") for r in manifest_refs),
            f"expected at least one ethics f_ref; got {sorted(manifest_refs)}",
        )


if __name__ == "__main__":
    unittest.main()
