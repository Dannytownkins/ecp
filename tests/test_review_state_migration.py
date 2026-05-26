import shutil
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path("scripts").resolve()))

from assembly.review_state import migrate_review_state, write_review_state


def test_review_state_v1_migration_is_noop():
    state = {"review_state_schema_version": 1}

    assert migrate_review_state(state) is state


def test_future_review_state_migration_raises():
    try:
        migrate_review_state({"review_state_schema_version": 99})
    except ValueError as exc:
        assert "newer editor" in str(exc)
    else:
        raise AssertionError("future review state should fail migration")


def test_overwrite_writes_backup(tmp_path):
    """Verify ``write_review_state(overwrite=True)`` copies the existing
    state to ``<name>.backup.json`` before overwriting.

    Test hygiene (2026-05-18): COPY the committed AWDMods fixture engagement
    into ``tmp_path`` before mutating. The previous version of this test
    mutated ``docs/ecp/2026-05-01-d5ebb62c/review-state-desktop.json`` in
    place and created a sibling ``.backup.json``, leaving the working tree
    dirty after every full pytest run. Codex caught the dirty diff (commit
    97f7825 follow-up) — fix is to run the mutation against an isolated
    copy.
    """
    source = Path("docs/ecp/2026-05-01-d5ebb62c")
    if not source.exists():
        pytest.skip("AWDMods fixture engagement (docs/ecp/2026-05-01-d5ebb62c) not present; restore it locally to run this overwrite test")
    engagement = tmp_path / "engagement"
    shutil.copytree(source, engagement)

    out = engagement / "review-state-desktop.json"
    if not out.exists():
        write_review_state(engagement, "desktop", plugin_root=Path("."))
    before = out.read_text(encoding="utf-8")
    out.write_text(before.replace('"needs_review"', '"approved"', 1), encoding="utf-8")

    write_review_state(engagement, "desktop", plugin_root=Path("."), overwrite=True)

    backup = engagement / "review-state-desktop.backup.json"
    assert backup.exists()
    assert '"approved"' in backup.read_text(encoding="utf-8")
