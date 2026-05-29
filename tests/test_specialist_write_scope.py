"""Source guard: the v2 specialist prompt must explicitly scope a specialist's
writes to its own emission file and forbid lead-owned files (G25 follow-up,
2026-05-29).

The pipeline has no write-attribution, so the prompt is the real control point
for the file-ownership invariant (contracts/lead-discipline.md). Engagement
docs/ecp/2026-05-28-e4050c0e saw a content-seo specialist write the lead's
lead-reflection.md. This guard fails if the explicit write-scope prohibition is
removed from the template. Behavioral enforcement (LLM compliance) can't be
unit-tested; the lead_reflection_well_formed canary is the post-hoc backstop.
"""
from __future__ import annotations

import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_PROMPT = (_REPO / "contracts" / "specialist-prompt-v2.md").read_text(encoding="utf-8")


class TestSpecialistWriteScope(unittest.TestCase):
    def test_scope_rule_present(self):
        self.assertIn("EXACTLY ONE file", _PROMPT)
        self.assertIn("MUST NOT", _PROMPT)

    def test_lead_owned_files_enumerated(self):
        for name in (
            "lead-reflection.md",
            "lead-state.json",
            "meta.json",
            "audit-desktop.md",
            "audit-mobile.md",
            "synthesizer-emission-v1.json",
            "ethics-findings.json",
        ):
            with self.subTest(file=name):
                self.assertIn(name, _PROMPT)

    def test_notes_redirect_and_contract_reference(self):
        self.assertIn("notes[]", _PROMPT)
        self.assertIn("lead-discipline.md", _PROMPT)


if __name__ == "__main__":
    unittest.main()
