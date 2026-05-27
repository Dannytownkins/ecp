"""Pre-validation autofix for cluster + ethics emissions (G15 P1-3).

The specialist subagents that emit cluster-emission-v1.json and
ethics-findings.json bounce on a small set of known shape traps that
appear across runs. Each bounce costs a retry dispatch + lead nudge +
~30-90s of wall-clock. Three live runs on the same URL
(``docs/ecp/2026-05-27-{b0051311,af72a2ae,52f53a53}``) catalogued the
exact shapes:

- ``telemetry.reference_files_read`` entries prefixed with
  ``references/`` (specialist quoted the path verbatim instead of the
  bare filename the schema expects).
- Duplicate ``(surface, baton_index, verdict)`` tuples — the specialist
  emitted two findings about the same surface/element/verdict triple
  (e.g., two "global-nav / e7 / FAIL" entries).
- ``proposed_anchor.reason`` over the 200-character schema cap.
- ``element.baton_index='absent'`` findings missing the required
  ``proposed_anchor`` field — the schema makes proposed_anchor MANDATORY
  for absent-anchored findings, and Layer-3 hotspot routing breaks
  without it.

This module applies semantically-conservative repairs to these specific
failure modes without changing the actual finding content. The lead
runs autofix BEFORE the schema validator; anything autofix can't
repair (out-of-enum verdicts, missing required prose, etc.) still
bounces the specialist as before.

The autofix's repair log is the audit trail: every change is recorded
with ``{finding_local_id, field, before, after, why}`` so the operator
can verify nothing material was rewritten. An empty repairs list means
the emission was already clean — autofix is idempotent.

Authored G15 P1-3 (2026-05-27).
"""
from __future__ import annotations

import copy
from typing import Any


# Schema cap for proposed_anchor.reason. The synthesizer prompt already
# tells specialists to keep this under 200 chars; the autofix is the
# safety net for when the specialist exceeds it anyway.
PROPOSED_ANCHOR_REASON_MAX_LEN = 200


# The default proposed_anchor injected when an absent-anchored finding
# omits one. Uses the kind="section" variant per schema/finding-v1.json:
#   - placement enum allowed for kind=section: {section-bottom-overlay,
#     after-section}; section-bottom-overlay is the "lives inside this
#     section near its bottom" semantic that operators normalize absent
#     findings to in practice (per multiple live-run lead-reflections).
#   - section_index=0 anchors at the first baton section, which exists
#     on every captured page (acquirer always emits ≥1 section).
#   - viewport: derived from the finding's device field; ethics page-
#     scope findings default to desktop.
# The reason string carries the auto-inject marker so it's findable in
# both the editor's "Place manually" queue and the engagement audit trail.
#
# Bug fix history: prior to 2026-05-27 this default was
# {kind=viewport, placement=above-fold-banner, viewport=both} — three
# schema-invalid choices that bounced the SAME absent finding right back
# into the validator on retry. Caught by five live runs in a row
# (docs/ecp/2026-05-27-{b0051311,625832a6,4a0721e9,0669899d,...} lead-
# reflections all hand-normalized the broken default). The fix matches
# the lead's manual normalization recipe.
_AUTO_INJECTED_PROPOSED_ANCHOR_REASON = (
    "auto-injected by emission_autofix: specialist omitted proposed_anchor "
    "on absent finding; operator must verify or replace in editor"
)


def _viewport_for_finding(finding: dict) -> str:
    """Pick a schema-valid viewport ('desktop' or 'mobile') for an
    injected proposed_anchor based on the finding's device field.
    Ethics (device='page') and unknown defaults to 'desktop' since the
    editor's manual-place queue is most often opened on desktop."""
    device = (finding.get("device") or "").lower()
    return "mobile" if device == "mobile" else "desktop"


def autofix_emission(emission: dict) -> tuple[dict, list[dict]]:
    """Apply pre-validation autofix repairs to a cluster/ethics emission.

    Returns ``(fixed_emission, repairs)`` where ``fixed_emission`` is a
    deep copy with repairs applied and ``repairs`` is a list of records
    describing every change. ``fixed_emission == emission`` is **not**
    guaranteed by Python equality; use the repairs list (empty = no
    change) as the source of truth for "was anything repaired?".

    Repairs applied (each one independent — running them in any order
    produces the same result; autofix runs them in the order listed):

    1. **Path-form telemetry strip.** ``telemetry.reference_files_read``
       entries that start with ``references/`` get the prefix stripped.
       Multi-segment paths (e.g., ``references/sub/file.md``) keep
       everything after ``references/`` — the schema expects bare
       references-relative filenames.
    2. **Duplicate finding dedup.** Findings sharing the same
       ``(surface, baton_index, verdict)`` triple are deduped; the
       earliest-occurring one wins. ``local_id`` values on survivors
       are *not* renumbered (preserving the specialist's authored
       sequence; renumbering would mask audit-trail intent).
    3. **proposed_anchor.reason cap.** Reason strings over
       ``PROPOSED_ANCHOR_REASON_MAX_LEN`` characters truncate at the
       last whole word boundary at or below the cap, with a trailing
       ``...`` ellipsis marker.
    4. **Missing proposed_anchor on absent findings.** When a finding
       has ``element.baton_index='absent'`` AND no ``proposed_anchor``
       field, a schema-valid section-variant default is injected:
       ``{kind: 'section', section_index: 0, placement:
       'section-bottom-overlay', viewport: <derived>, reason: <auto-
       inject marker>}``. The marker reason makes the auto-injection
       visible to the operator in the editor's "Place manually" queue
       so they verify/replace placement before client delivery.
       ``viewport`` derives from ``finding.device`` (mobile finding →
       mobile; desktop or ethics-page → desktop).

    Idempotency: re-running autofix on an already-fixed emission
    produces an empty repairs list (every repair-guard short-circuits
    when the data is already correct).

    Notes on what autofix does NOT do (deliberate non-scope):

    - **No enum coercion.** ``effort.change_type`` values like
      ``"template"`` or ``"content"`` that don't match the schema enum
      are NOT mapped to nearest-valid synonyms — that risks silently
      changing the meaning of the finding. Schema validation still
      bounces these, by design.
    - **No registry reconciliation.** When ``baton_index`` resolves in
      the actual baton but not in the candidate registry, this v1 does
      not auto-flag ``intentional_outside_registry``. That repair
      requires loading the baton + registry sidecar and is a separate
      planned extension (G15 P1-3 v2).
    - **No additional-property strip.** Keys like ``template_id`` or
      ``expected_overlay`` that violate ``additionalProperties: false``
      are NOT removed — they often signal an emission-shape drift the
      specialist itself needs to learn from. The bounce-and-retry
      surfaces this for the prompt-tightening feedback loop.
    """
    fixed = copy.deepcopy(emission)
    repairs: list[dict] = []

    _repair_telemetry_paths(fixed, repairs)
    _repair_duplicate_findings(fixed, repairs)
    _repair_overlong_proposed_anchor_reasons(fixed, repairs)
    _repair_missing_proposed_anchor_on_absent(fixed, repairs)

    return fixed, repairs


# ---------------------------------------------------------------------------
# Repair 1 — telemetry.reference_files_read path-prefix strip
# ---------------------------------------------------------------------------


def _repair_telemetry_paths(emission: dict, repairs: list[dict]) -> None:
    telemetry = emission.get("telemetry")
    if not isinstance(telemetry, dict):
        return
    paths = telemetry.get("reference_files_read")
    if not isinstance(paths, list):
        return
    new_paths: list[str] = []
    for p in paths:
        if isinstance(p, str) and p.startswith("references/"):
            stripped = p[len("references/"):]
            new_paths.append(stripped)
            repairs.append({
                "finding_local_id": None,
                "field": "telemetry.reference_files_read[]",
                "before": p,
                "after": stripped,
                "why": (
                    "Path-form telemetry entry; the schema expects bare "
                    "references-relative filenames (e.g., 'ethics-gate.md', "
                    "not 'references/ethics-gate.md')."
                ),
            })
        else:
            new_paths.append(p)
    telemetry["reference_files_read"] = new_paths


# ---------------------------------------------------------------------------
# Repair 2 — duplicate finding dedup
# ---------------------------------------------------------------------------


def _finding_dedup_key(finding: dict) -> tuple[str, str, str] | None:
    """Key for ``(surface, baton_index, verdict)`` dedup. Returns None
    when any component is missing so the finding isn't accidentally
    deduped against another missing-key entry."""
    surface = finding.get("surface")
    verdict = finding.get("verdict")
    element = finding.get("element") or {}
    baton_index = element.get("baton_index") if isinstance(element, dict) else None
    if not (isinstance(surface, str) and isinstance(verdict, str) and isinstance(baton_index, str)):
        return None
    return (surface, baton_index, verdict)


def _repair_duplicate_findings(emission: dict, repairs: list[dict]) -> None:
    findings = emission.get("findings")
    if not isinstance(findings, list):
        return
    seen: dict[tuple[str, str, str], int] = {}
    kept: list[dict] = []
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            kept.append(f)
            continue
        key = _finding_dedup_key(f)
        if key is None:
            kept.append(f)
            continue
        if key in seen:
            repairs.append({
                "finding_local_id": f.get("local_id"),
                "field": "findings[]",
                "before": f"duplicate of local_id={findings[seen[key]].get('local_id')!r} on (surface={key[0]!r}, baton_index={key[1]!r}, verdict={key[2]!r})",
                "after": "<dropped>",
                "why": (
                    "Duplicate (surface, baton_index, verdict) tuple; "
                    "kept the earlier-occurring finding to preserve "
                    "specialist sequencing."
                ),
            })
            continue
        seen[key] = i
        kept.append(f)
    emission["findings"] = kept


# ---------------------------------------------------------------------------
# Repair 3 — proposed_anchor.reason length cap
# ---------------------------------------------------------------------------


def _truncate_at_word_boundary(text: str, max_len: int) -> str:
    """Truncate ``text`` at the last whitespace boundary at or below
    ``max_len - 3`` (room for the ``...`` marker). Falls back to a hard
    truncate at ``max_len - 3`` if no boundary exists."""
    if len(text) <= max_len:
        return text
    headroom = max_len - 3  # leave room for ellipsis marker
    if headroom <= 0:
        return text[:max_len]
    candidate = text[:headroom]
    last_space = candidate.rfind(" ")
    if last_space >= 0:
        candidate = candidate[:last_space]
    return candidate.rstrip(" .,;:") + "..."


def _repair_overlong_proposed_anchor_reasons(
    emission: dict, repairs: list[dict],
) -> None:
    findings = emission.get("findings")
    if not isinstance(findings, list):
        return
    for f in findings:
        if not isinstance(f, dict):
            continue
        pa = f.get("proposed_anchor")
        if not isinstance(pa, dict):
            continue
        reason = pa.get("reason")
        if not isinstance(reason, str):
            continue
        if len(reason) <= PROPOSED_ANCHOR_REASON_MAX_LEN:
            continue
        truncated = _truncate_at_word_boundary(reason, PROPOSED_ANCHOR_REASON_MAX_LEN)
        pa["reason"] = truncated
        repairs.append({
            "finding_local_id": f.get("local_id"),
            "field": "proposed_anchor.reason",
            "before": f"{len(reason)} chars: {reason[:80]!r}...",
            "after": f"{len(truncated)} chars: {truncated!r}",
            "why": (
                f"proposed_anchor.reason exceeds the {PROPOSED_ANCHOR_REASON_MAX_LEN}-char "
                f"schema cap; truncated at the last word boundary."
            ),
        })


# ---------------------------------------------------------------------------
# Repair 4 — inject default proposed_anchor for absent findings
# ---------------------------------------------------------------------------


def _repair_missing_proposed_anchor_on_absent(
    emission: dict, repairs: list[dict],
) -> None:
    findings = emission.get("findings")
    if not isinstance(findings, list):
        return
    for f in findings:
        if not isinstance(f, dict):
            continue
        element = f.get("element") or {}
        if not isinstance(element, dict):
            continue
        if element.get("baton_index") != "absent":
            continue
        if "proposed_anchor" in f and isinstance(f["proposed_anchor"], dict):
            continue  # already has one
        viewport = _viewport_for_finding(f)
        f["proposed_anchor"] = {
            "kind": "section",
            "section_index": 0,
            "placement": "section-bottom-overlay",
            "viewport": viewport,
            "reason": _AUTO_INJECTED_PROPOSED_ANCHOR_REASON,
        }
        repairs.append({
            "finding_local_id": f.get("local_id"),
            "field": "proposed_anchor",
            "before": "<missing>",
            "after": (
                "auto-injected schema-valid section variant "
                f"(section_index=0, section-bottom-overlay, viewport={viewport})"
            ),
            "why": (
                "absent-anchored finding lacks the schema-required "
                "proposed_anchor; injected a section-bottom-overlay default "
                "at section_index=0 with an auto-inject marker so the "
                "operator must verify placement in the editor's "
                "'Place manually' queue."
            ),
        })


__all__ = [
    "PROPOSED_ANCHOR_REASON_MAX_LEN",
    "autofix_emission",
]
