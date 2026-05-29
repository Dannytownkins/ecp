"""Regression test for G13: no non-ASCII in `print()` string literals.

The operator runs on Windows, whose console defaults to cp1252. A `print()`
whose literal text contains a non-ASCII char (em-dash, arrow, section sign)
raises `UnicodeEncodeError` and crashes the script — observed in
`scripts/assembly/canary_checks.py` and across several runtime scripts
(`test-specialist.py`, `dom_preprocess.py`, `acquire_url.py`,
`ecp_configurator.py`). `json.dumps` output is safe (ensure_ascii defaults
True), but raw `print(f"... — ...")` status lines are not.

This lint scans every runtime script and asserts no `print()` literal carries a
non-ASCII char, preventing the whole class from recurring. (`scripts/one_off/`
is excluded — dated throwaway analysis, not part of the audit runtime.)
"""
import ast
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"


def _print_string_literals(tree: ast.AST):
    """Yield (lineno, value) for every str literal inside a `print(...)` call,
    including the literal segments of f-strings."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        ):
            for arg in node.args:
                for sub in ast.walk(arg):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                        yield getattr(sub, "lineno", node.lineno), sub.value


class TestNoNonAsciiInScriptPrints(unittest.TestCase):
    def test_print_literals_are_ascii(self):
        offenders: list[str] = []
        for py in SCRIPTS.rglob("*.py"):
            if "one_off" in py.parts:
                continue
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for lineno, val in _print_string_literals(tree):
                bad = sorted({c for c in val if ord(c) > 127})
                if bad:
                    offenders.append(f"{py.relative_to(REPO)}:{lineno}: {bad!r}")
        self.assertEqual(
            offenders,
            [],
            "non-ASCII in print() literals crashes cp1252 Windows consoles:\n"
            + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
