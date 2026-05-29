"""Regression: frozen Cursor agents must not sit in Claude Code's discovery scope.

Engagement ``docs/ecp/2026-05-28-e4050c0e`` surfaced the leak: the five
``ecp-*.md`` Cursor subagent prompts lived in the repo-root ``agents/``
directory, which Claude Code auto-discovers as selectable subagent types.
No ``skills/``, ``contracts/``, or ``workflows/`` file wires them in, yet the
audit lead could *see* them in the Agent tool's type list and inferred a
phantom delegation path -- it surfaced "Delegate to ecp-orchestrator
(Recommended)" as a dispatch option the canonical SKILL never authorizes.

``product.md`` §8 says Cursor is "archived, not shipped ... re-portable from
the archive"; §5 freezes the scope. To freeze that operationally we moved the
files to ``archive/cursor-agents/`` (out of discovery scope) rather than just
marking them out-of-scope in prose -- the same lesson as G16/G17/G22+G24.

This is a non-existence guard (mirrors G17's ``test_old_constant_is_gone``):
it fails if a future change re-introduces any discoverable Cursor agent file,
and it fails if the archived copies are deleted (which would lose the §8
re-portability the relocation preserves).

unittest-style for ``python -m unittest discover`` runner compatibility.

Run:
    python -m unittest tests.test_g21_cursor_agents_not_discoverable
"""
from __future__ import annotations

import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

_CURSOR_AGENT_STEMS = {
    "ecp-acquisition",
    "ecp-cluster-auditor",
    "ecp-orchestrator",
    "ecp-reviewer",
    "ecp-synthesizer",
}


class TestCursorAgentsNotDiscoverable(unittest.TestCase):
    def test_repo_root_agents_dir_has_no_discoverable_cursor_agents(self):
        """The repo-root ``agents/`` dir must not auto-expose Cursor agents.

        Empty/absent dir is fine; what must never recur is a discoverable
        ``agents/ecp-*.md`` file that Claude Code lists as a subagent type.
        """
        agents_dir = _REPO / "agents"
        if not agents_dir.exists():
            return  # absent dir => nothing discoverable; ideal end state
        leaked = sorted(
            p.name for p in agents_dir.glob("*.md") if p.stem in _CURSOR_AGENT_STEMS
        )
        self.assertEqual(
            leaked,
            [],
            "Cursor agent files leaked back into Claude Code discovery scope "
            f"(agents/): {leaked}. They are frozen per product.md §5/§8 and "
            "must live in archive/cursor-agents/.",
        )

    def test_archived_copies_are_preserved(self):
        """The archived copies must exist -- relocation, not deletion.

        §8 promises the Cursor runtime is "re-portable from the archive";
        deleting these would break that promise. The relocation keeps them.
        """
        archive_dir = _REPO / "archive" / "cursor-agents"
        self.assertTrue(
            archive_dir.is_dir(),
            "archive/cursor-agents/ is missing -- the frozen Cursor agents "
            "must be relocated there, not deleted (product.md §8).",
        )
        archived = {p.stem for p in archive_dir.glob("*.md")}
        missing = sorted(_CURSOR_AGENT_STEMS - archived)
        self.assertEqual(
            missing,
            [],
            f"archived Cursor agents missing from archive/cursor-agents/: {missing}",
        )


if __name__ == "__main__":
    unittest.main()
