"""Regression test for G11: the audit router must document the REAL v2 pipeline.

`skills/audit/SKILL.md` used to tell the lead to run `validate-cluster-files.py`
+ `assemble-audit.py` for assembly. Those are v1 markdown-path tools: on a v2
(JSON-emission) engagement they parse zero findings or raise FileNotFoundError
(`prep_synth_input.py` expects `cluster-*.md`). The real v2 spine is:

    test-specialist.py validate -> lead_prep.py build-canonical-frefs ->
    synth_input.trim_baton_file -> test-specialist.py prepare-synthesizer ->
    (synthesizer dispatch) -> test-specialist.py validate --schema
    synthesizer-emission -> test-specialist.py drift-check ->
    generate-report.py --v2

This test pins two things, browser-free:
  1. The router names the real v2 commands and frames the v1 tools as legacy.
  2. Every v2 command the router names actually EXISTS as a subcommand / flag /
     function in the scripts (doc<->code anti-drift guard). Rename a subcommand
     and this fails, forcing the doc to stay truthful.
"""
import ast
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / "skills" / "audit" / "SKILL.md"


def _add_parser_names(script: Path) -> set[str]:
    """Collect the string literal of every `*.add_parser("X")` call via AST."""
    tree = ast.parse(script.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_parser"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            names.add(node.args[0].value)
    return names


def _func_defs(script: Path) -> set[str]:
    tree = ast.parse(script.read_text(encoding="utf-8"))
    return {
        n.name
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _string_arg_literals(script: Path) -> set[str]:
    """All string-literal positional args anywhere (used to confirm flags)."""
    tree = ast.parse(script.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.add(node.value)
    return out


class TestRouterDocumentsV2Commands(unittest.TestCase):
    def setUp(self):
        self.skill = SKILL.read_text(encoding="utf-8")

    def test_names_the_real_v2_commands(self):
        for token in (
            "test-specialist.py validate",
            "lead_prep.py build-canonical-frefs",
            "prepare-synthesizer",
            "drift-check",
            "generate-report.py --v2",
        ):
            self.assertIn(token, self.skill, f"router must document v2 command: {token!r}")
        # The baton-trim step must be named (function or module).
        self.assertTrue(
            ("trim_baton_file" in self.skill) or ("synth_input" in self.skill),
            "router must document the synth_input baton-trim step",
        )

    def test_v1_tools_marked_legacy_not_used_as_steps(self):
        # v1 tools may be NAMED (as legacy) but must not be the instructed step.
        self.assertNotIn("python scripts/validate-cluster-files.py", self.skill)
        self.assertNotIn("python scripts/assemble-audit.py", self.skill)
        # And they must be explicitly framed as legacy somewhere.
        self.assertRegex(self.skill, r"(?i)legacy")
        for v1 in ("validate-cluster-files.py", "assemble-audit.py"):
            self.assertIn(v1, self.skill, f"{v1} should be named in the legacy note")


class TestV2CommandsExistInCode(unittest.TestCase):
    """Anti-drift: each documented v2 command must resolve to real code."""

    def test_test_specialist_subcommands(self):
        names = _add_parser_names(REPO / "scripts" / "test-specialist.py")
        for sub in ("validate", "prepare-synthesizer", "drift-check"):
            self.assertIn(sub, names, f"test-specialist.py must expose `{sub}`")

    def test_lead_prep_subcommand(self):
        names = _add_parser_names(REPO / "scripts" / "lead_prep.py")
        self.assertIn("build-canonical-frefs", names)

    def test_generate_report_has_v2_flag(self):
        flags = _string_arg_literals(REPO / "scripts" / "generate-report.py")
        self.assertIn("--v2", flags)

    def test_synth_input_exposes_trim(self):
        self.assertIn(
            "trim_baton_file", _func_defs(REPO / "scripts" / "assembly" / "synth_input.py")
        )


if __name__ == "__main__":
    unittest.main()
