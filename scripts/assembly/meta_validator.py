"""meta.json validator — catches silent-corruption bugs in engagement state.

Codex's MEDIUM M2 finding: ``docs/ecp/2026-04-15-36bf19a6/meta.json`` has
``devices_scanned`` written twice (lines 9 and 15), and Python's ``json.load``
silently keeps only the last occurrence — so the real list (e.g.
``["desktop", "mobile"]``) gets overwritten by a stale ``[]``. The pipeline
then treats the engagement as "no devices scanned" even though the audits
are sitting right there on disk.

This module detects two classes of meta.json corruption:

1. **Duplicate keys** — same key written twice at the same object level.
   Silently drops data under ``json.load`` default behavior. Detected via
   ``object_pairs_hook`` which receives the raw key-value sequence before
   dedup.

2. **Invariant violations** — post-phase state that should be impossible.
   Example: ``phase: "audit"`` but ``devices_scanned: []`` — a completed
   audit phase must have at least one device.

The validator WARNS rather than fails: these are diagnostics that help
the operator notice corruption, not hard blockers on pipeline execution.
A stricter fail-loud mode could be added later once we're confident
there are no legitimate false positives.

Related: skills/audit/SKILL.md lead workflow should be updated to
read-then-write meta.json incrementally rather than overwriting the
whole file each phase. That's the upstream fix; this module is the
downstream safety net.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple


def _parse_with_duplicate_detection(text: str) -> Tuple[dict, List[str]]:
    """Parse JSON text and return ``(data, duplicate_keys_found)``.

    Uses ``json.loads(..., object_pairs_hook=...)`` to inspect the raw
    key-value sequence BEFORE Python coerces it to a dict (which would
    silently drop duplicates). The hook runs once per object in the
    JSON tree; we flatten duplicates across all objects into a single
    list with nested-path annotations.

    Returns the final parsed dict (same shape as ``json.loads``) along
    with a list of duplicate key names encountered. Empty list means
    the JSON is structurally clean.

    Limitation: the hook doesn't know where in the tree it is — we
    capture the key name but not a full dotted path. For meta.json
    (a flat object) this is fine; for deeply nested JSON a richer
    walker would be better.
    """
    duplicates: List[str] = []

    def hook(pairs):
        seen_keys: set = set()
        result: dict = {}
        for k, v in pairs:
            if k in seen_keys:
                duplicates.append(k)
            seen_keys.add(k)
            result[k] = v  # last-write-wins (matches json.load default)
        return result

    data = json.loads(text, object_pairs_hook=hook)
    return data, duplicates


def validate_meta_json(meta_path: Path) -> List[str]:
    """Validate a meta.json file and return a list of human-readable warnings.

    Empty list means the file is clean. Each warning string describes one
    specific issue so the caller can print them individually to stderr.

    Checks performed:

    - File exists + parses as valid JSON (parse errors returned as a
      single warning, downstream checks skipped).
    - No duplicate keys at any object level (the M2 bug surface).
    - ``devices_requested`` and ``devices_scanned`` are lists when present.
    - Invariant: if ``phase`` is ``audit``/``plan``/``review``/``build``/``complete``,
      ``devices_scanned`` should be non-empty.
    - Invariant: ``devices_scanned`` should be a subset of (or equal to)
      ``devices_requested`` when both are non-empty.

    Example output:

        ['duplicate key "devices_scanned" detected (last-write-wins '
         'truncated earlier value)',
         'phase="audit" but devices_scanned is empty — likely the '
         'duplicate-key bug from M2']
    """
    warnings: List[str] = []

    if not meta_path.exists():
        warnings.append(f"meta.json not found at {meta_path}")
        return warnings

    try:
        text = meta_path.read_text(encoding="utf-8")
    except (OSError, IOError) as exc:
        warnings.append(f"meta.json at {meta_path} could not be read: {exc}")
        return warnings

    try:
        data, dupes = _parse_with_duplicate_detection(text)
    except json.JSONDecodeError as exc:
        warnings.append(f"meta.json at {meta_path} is not valid JSON: {exc}")
        return warnings

    # Duplicate-key check — the direct M2 trigger.
    for key in dupes:
        warnings.append(
            f'duplicate key "{key}" detected in {meta_path.name} '
            "(JSON silently kept only the last occurrence — earlier "
            "value was lost; see Codex M2)"
        )

    # Field-shape checks — only warn if the field exists.
    for field in ("devices_requested", "devices_scanned", "clusters_used"):
        if field in data and not isinstance(data[field], list):
            warnings.append(
                f'meta.json field "{field}" should be a list, got '
                f"{type(data[field]).__name__}"
            )

    # report_state enum check (product.md §6 draft -> client-ready gate).
    # Only warn if present; missing is treated as "draft" by readers.
    if "report_state" in data and data["report_state"] not in ("draft", "client-verified"):
        warnings.append(
            f'meta.json field "report_state" must be "draft" or '
            f'"client-verified", got {data["report_state"]!r} (product.md §6)'
        )

    # reflection_state enum check (G23, 2026-05-28). Mirror of report_state:
    # only warn if present; missing/blank is treated as "draft" by readers.
    if "reflection_state" in data and data["reflection_state"] not in ("draft", "complete"):
        warnings.append(
            f'meta.json field "reflection_state" must be "draft" or '
            f'"complete", got {data["reflection_state"]!r} (G23)'
        )

    # Invariant: completed phases must have at least one device scanned.
    phase = data.get("phase")
    devices_scanned = data.get("devices_scanned") if isinstance(data.get("devices_scanned"), list) else None
    devices_requested = data.get("devices_requested") if isinstance(data.get("devices_requested"), list) else None

    active_phases = {"audit", "plan", "review", "build", "complete"}
    if phase in active_phases and devices_scanned is not None and not devices_scanned:
        warnings.append(
            f'phase="{phase}" but devices_scanned is empty — this is the '
            "signature of the M2 duplicate-key bug (the real device list "
            "was overwritten by a second empty write). Check the file for "
            "duplicate devices_scanned entries."
        )

    # Invariant: scanned should be a subset of requested when both present.
    if (
        devices_scanned
        and devices_requested
        and not set(devices_scanned).issubset(set(devices_requested))
    ):
        extra = sorted(set(devices_scanned) - set(devices_requested))
        warnings.append(
            f"devices_scanned contains devices not in devices_requested: {extra}. "
            "Either the engagement was re-scoped or meta.json got crossed up."
        )

    return warnings
