"""Draft -> Complete reflection-state gate (G23, 2026-05-28).

A `lead-reflection.md` is always a DRAFT until the lead explicitly
attests that the audit pipeline finished and the narrative reflects
the final on-disk state.

Why this exists: engagement `docs/ecp/2026-05-28-e4050c0e` saw
`lead-reflection.md` written at specialist-phase time (~16:18Z) by an
agent acting prematurely — at the moment of write, the agent's local
view said "5 of 6 desktop, 0 of 6 mobile, synth did not run, ethics
did not run." Each of those was *true at write time* but the pipeline
continued for another 42 minutes and completed cleanly. The reflection
was never refreshed, so the operator read a "we failed" narrative
against an actually-clean deliverable.

The G8 ``report_state`` machine has exactly this shape for the
client-ready gate: a default ``draft`` state, a deliberate manual
attestation via an explicit CLI verb, and an ``AutoPromotionError``
that refuses to mark state on automated runs. G23 instantiates the
same pattern for reflections.

The state lives in ``meta.json`` as
``reflection_state: "draft" | "complete"``. Missing/blank reads as
``draft`` (back-compat with engagements created before this field
existed).

The load-bearing invariant: **automated / ``--auto`` execution can
NEVER mark a reflection complete.** This isn't because automation is
forbidden — it's because *premature finalization is the failure
mode we're guarding against.* Marking complete is the lead's explicit
attestation that the on-disk reflection narrative matches the
pipeline's actual end-state. Automation by definition can't make that
attestation; a human (operator) or the lead at the END of its own
final review can.

Mirror of `scripts/assembly/report_state.py` (G8, product.md §6).
The two state machines are independent — `report_state` is the
draft → client-verified gate for the *deliverable*, `reflection_state`
is the draft → complete gate for the *narrative about how the
deliverable was produced*. Both default to draft; both flip via
explicit operator action; neither can be flipped under `--auto`.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .atomic_write import atomic_write_json

REFLECTION_STATE_DRAFT = "draft"
REFLECTION_STATE_COMPLETE = "complete"
VALID_REFLECTION_STATES = (REFLECTION_STATE_DRAFT, REFLECTION_STATE_COMPLETE)


class AutoCompletionError(PermissionError):
    """Raised when automated/--auto execution tries to mark a
    reflection complete.

    Distinct from G8's ``AutoPromotionError`` so the two state machines'
    error paths don't conflate (a caller may want to catch one and not
    the other). Both subclass ``PermissionError`` so generic
    "permission denied" handlers still catch them.
    """


def read_reflection_state(meta: dict[str, Any]) -> str:
    """Return the reflection_state, defaulting to ``draft`` (G23).

    Missing, null, blank, or any unrecognized value reads as
    ``draft`` — a reflection is never marked complete unless something
    explicitly and validly set it so. Mirror of
    ``report_state.read_report_state``.
    """
    value = meta.get("reflection_state")
    return value if value in VALID_REFLECTION_STATES else REFLECTION_STATE_DRAFT


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def set_reflection_complete(
    meta_path: str | Path,
    *,
    auto: bool = False,
    now: str | None = None,
) -> dict[str, Any]:
    """Mark the engagement's reflection narrative ``complete`` — the
    lead's explicit attestation that ``lead-reflection.md`` matches
    the pipeline's actual end-state.

    Args:
        meta_path: path to the engagement's ``meta.json``.
        auto: True when running under ``--auto`` / any automated chain.
            When True this raises ``AutoCompletionError`` — automated
            execution can never mark a reflection complete (G23).
        now: ISO 8601 timestamp for the ``updated`` field; defaults to
            now.

    Returns the updated meta dict. Writes back atomically via
    ``atomic_write_json``, mirroring the
    ``report_state.set_client_verified`` write contract.
    """
    if auto:
        raise AutoCompletionError(
            "Refusing to mark reflection complete under --auto: "
            "completion requires a manual attestation that the on-disk "
            "reflection narrative matches the pipeline's actual end-state "
            "(G23). Premature finalization is the failure mode this guard "
            "exists to prevent; automated execution can never make that "
            "attestation."
        )

    meta_path = Path(meta_path)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["reflection_state"] = REFLECTION_STATE_COMPLETE
    meta["updated"] = now or _utc_now()
    atomic_write_json(meta_path, meta)
    return meta


__all__ = [
    "AutoCompletionError",
    "REFLECTION_STATE_COMPLETE",
    "REFLECTION_STATE_DRAFT",
    "VALID_REFLECTION_STATES",
    "read_reflection_state",
    "set_reflection_complete",
]
