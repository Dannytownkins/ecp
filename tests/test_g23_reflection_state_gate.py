"""G23 regression: lead-reflection draft → complete state gate.

A `lead-reflection.md` is always a DRAFT until the lead explicitly
attests via `generate-report.py --mark-reflection-complete` that the
narrative on disk matches the pipeline's actual end-state.

Why this matters: engagement `docs/ecp/2026-05-28-e4050c0e` saw the
reflection written prematurely by an agent acting on a stale-partial
view (5 of 6 specialists landed, no synth yet, no ethics yet). The
content was true at write time but became misleading 42 minutes later
when the pipeline actually completed cleanly. The G23 state machine
prevents that premature-finalization failure mode by separating
"someone wrote to the file" (cheap, anyone can do) from "the lead
attests the narrative is final" (deliberate, gated, refuses under
--auto).

Mirror of `tests/test_g8_client_verified_gate.py` (the G8 pattern G23
adapts). unittest-style for `python -m unittest discover` runner
compatibility.

Run:
    python -m unittest tests.test_g23_reflection_state_gate
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts"))

from assembly.reflection_state import (  # noqa: E402
    AutoCompletionError,
    REFLECTION_STATE_COMPLETE,
    REFLECTION_STATE_DRAFT,
    read_reflection_state,
    set_reflection_complete,
)


def _meta(reflection_state: str | None = None) -> dict:
    base = {
        "id": "test-engagement",
        "page": {"url": "https://example.com", "type": "product"},
        "platform": "test",
        "schema_version": 3,
        "type": "audit",
        "report_state": "draft",
    }
    if reflection_state is not None:
        base["reflection_state"] = reflection_state
    return base


class TestReadReflectionState(unittest.TestCase):
    def test_missing_field_reads_as_draft(self):
        """Back-compat with engagements created before G23 — absent
        reflection_state must read as draft, never complete."""
        self.assertEqual(read_reflection_state({}), REFLECTION_STATE_DRAFT)
        self.assertEqual(
            read_reflection_state(_meta()), REFLECTION_STATE_DRAFT
        )

    def test_null_or_blank_reads_as_draft(self):
        for value in (None, "", " ", "  "):
            with self.subTest(value=value):
                self.assertEqual(
                    read_reflection_state({"reflection_state": value}),
                    REFLECTION_STATE_DRAFT,
                )

    def test_unknown_value_reads_as_draft(self):
        """Defense in depth: if a future field value (e.g. "in-review")
        ever slips in, readers must NOT silently treat it as complete.
        Draft-by-default is the safe interpretation."""
        for value in ("in-review", "pending", "yes", "true", "completed"):
            with self.subTest(value=value):
                self.assertEqual(
                    read_reflection_state({"reflection_state": value}),
                    REFLECTION_STATE_DRAFT,
                )

    def test_valid_values_round_trip(self):
        self.assertEqual(
            read_reflection_state({"reflection_state": "draft"}),
            REFLECTION_STATE_DRAFT,
        )
        self.assertEqual(
            read_reflection_state({"reflection_state": "complete"}),
            REFLECTION_STATE_COMPLETE,
        )


class TestSetReflectionComplete(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.eng = Path(self.tmp.name) / "engagement"
        self.eng.mkdir()
        self.meta_path = self.eng / "meta.json"
        self.meta_path.write_text(json.dumps(_meta()), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_marks_meta_complete_when_auto_false(self):
        result = set_reflection_complete(self.meta_path, auto=False)
        self.assertEqual(result["reflection_state"], REFLECTION_STATE_COMPLETE)
        on_disk = json.loads(self.meta_path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["reflection_state"], REFLECTION_STATE_COMPLETE)
        # `updated` timestamp gets refreshed.
        self.assertIn("updated", on_disk)

    def test_refuses_under_auto(self):
        """The load-bearing invariant: --auto execution can NEVER mark
        reflection complete. This is the whole point of the gate —
        premature finalization is the failure mode it exists to prevent."""
        with self.assertRaises(AutoCompletionError):
            set_reflection_complete(self.meta_path, auto=True)
        # State must remain draft after the refused call.
        on_disk = json.loads(self.meta_path.read_text(encoding="utf-8"))
        self.assertEqual(
            read_reflection_state(on_disk), REFLECTION_STATE_DRAFT,
            "Refused mark-complete attempt must leave state at draft.",
        )

    def test_auto_completion_error_is_a_permission_error(self):
        """Generic 'permission denied' handlers (e.g. a callsite that
        wraps both G8 and G23 verbs in one try/except) must still catch
        the refusal."""
        try:
            set_reflection_complete(self.meta_path, auto=True)
        except PermissionError:
            pass
        else:
            self.fail("AutoCompletionError must subclass PermissionError.")

    def test_explicit_now_timestamp_used(self):
        result = set_reflection_complete(
            self.meta_path, auto=False, now="2026-05-28T12:00:00Z",
        )
        self.assertEqual(result["updated"], "2026-05-28T12:00:00Z")


class TestMarkReflectionCompleteCLI(unittest.TestCase):
    """End-to-end exercise of the `--mark-reflection-complete` verb on
    `generate-report.py`. Mirrors the G8 `--mark-client-verified` CLI
    test surface."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.eng = Path(self.tmp.name) / "engagement"
        self.eng.mkdir()
        self.meta_path = self.eng / "meta.json"
        self.meta_path.write_text(json.dumps(_meta()), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _run_cli(self, *args: str) -> subprocess.CompletedProcess:
        # --device + --plugin-root are required by argparse globally but
        # are unused by the --mark-reflection-complete code path
        # (mirrors G8 test_g8_client_verified_gate.py:_run_cli).
        return subprocess.run(
            [
                sys.executable,
                str(_REPO / "scripts" / "generate-report.py"),
                "--engagement", str(self.eng),
                "--device", "laptop",
                "--plugin-root", str(_REPO),
                *args,
            ],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )

    def test_cli_marks_complete_and_exits_zero(self):
        result = self._run_cli("--mark-reflection-complete")
        self.assertEqual(
            result.returncode, 0,
            f"Clean --mark-reflection-complete must exit 0. "
            f"stderr={result.stderr!r}",
        )
        on_disk = json.loads(self.meta_path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["reflection_state"], REFLECTION_STATE_COMPLETE)
        self.assertIn("reflection_state set to complete", result.stdout)

    def test_cli_refuses_under_auto_and_exits_nonzero(self):
        result = self._run_cli("--mark-reflection-complete", "--auto")
        self.assertEqual(
            result.returncode, 2,
            f"--mark-reflection-complete --auto must exit 2 (refused). "
            f"stderr={result.stderr!r}",
        )
        # File must NOT have been promoted.
        on_disk = json.loads(self.meta_path.read_text(encoding="utf-8"))
        self.assertEqual(
            read_reflection_state(on_disk), REFLECTION_STATE_DRAFT,
            "Auto-refused CLI invocation must leave state at draft.",
        )
        # Stderr must explain why.
        self.assertIn("ERROR", result.stderr)
        self.assertIn("premature finalization", result.stderr.lower())


class TestG23DoesNotEntangleWithG8(unittest.TestCase):
    """The two state machines are independent: flipping reflection_state
    must not touch report_state, and vice versa. A regression that
    accidentally coupled the two would be silent and serious."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.eng = Path(self.tmp.name) / "engagement"
        self.eng.mkdir()
        self.meta_path = self.eng / "meta.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_marking_reflection_complete_does_not_touch_report_state(self):
        self.meta_path.write_text(
            json.dumps({**_meta(), "report_state": "draft"}),
            encoding="utf-8",
        )
        set_reflection_complete(self.meta_path, auto=False)
        on_disk = json.loads(self.meta_path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["report_state"], "draft")
        self.assertEqual(on_disk["reflection_state"], REFLECTION_STATE_COMPLETE)


if __name__ == "__main__":
    unittest.main()
