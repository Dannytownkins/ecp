"""Regression test for G12: the Claude acquirer must steer eval through base64.

`workflows/acquire.md` is the Claude `/ecp:audit` acquirer. It runs `agent-browser
eval` via the Bash tool. On Windows, `agent-browser` resolves to a `.ps1`/`.cmd`
npm shim that re-parses argv; PowerShell does not treat CMD-style `\"` as an
escape, so a raw quoted JS payload truncates -> `SyntaxError: Unexpected end of
input`. The deterministic acquirer already fixed this in `scripts/acquire_url.py`
(`_eval_args` -> `agent-browser eval -b <base64>`); the Claude acquirer dodged it
only by environment luck (the bash shim). This pins the documented guard so it
can't silently regress, browser-free.
"""
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ACQUIRE = REPO / "workflows" / "acquire.md"


class TestAcquireEvalGuard(unittest.TestCase):
    def setUp(self):
        self.doc = ACQUIRE.read_text(encoding="utf-8")
        self.lower = self.doc.lower()

    def test_documents_base64_eval_mechanism(self):
        # The fix: base64-encode non-trivial JS and pass it with -b (or --stdin).
        self.assertIn("eval -b", self.doc, "must steer eval through `eval -b <base64>`")
        self.assertIn("base64", self.lower)
        self.assertIn("--stdin", self.doc, "must mention the --stdin alternative")

    def test_records_the_windows_root_cause(self):
        # Keep the WHY so a future editor doesn't strip the guard as redundant.
        self.assertTrue(
            (".ps1" in self.lower) or ("powershell" in self.lower),
            "must explain the Windows .ps1/PowerShell shim cause",
        )
        self.assertIn("syntaxerror", self.lower)
        self.assertIn("unexpected end of input", self.lower)

    def test_cross_references_the_acquirer_fix(self):
        # Single-source-of-truth: point at the verified acquirer-path fix.
        self.assertIn("acquire_url.py", self.doc)
        self.assertTrue(
            ("_eval_args" in self.doc) or ("_unwrap_eval" in self.doc),
            "must reference the canonical eval helper(s)",
        )

    def test_scopes_the_rule_trivial_inline_allowed(self):
        # A bare property read may stay inline; only richer JS needs base64.
        self.assertIn("document.title", self.doc)


if __name__ == "__main__":
    unittest.main()
