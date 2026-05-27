"""Visual evidence taxonomy (Phase 2 — 2026-05-18).

Separates FINDING IDENTITY from HOW THE REPORT REPRESENTS IT VISUALLY.

The pre-Phase-2 renderer inferred visual treatment from ``baton_index`` and
``match_method`` alone. This caused absent findings (no sticky CTA, no reviews
block, no payment badges near purchase zone) to render as generic circular
proxy markers planted on whatever element happened to be nearby — producing
visually meaningless evidence even though the finding itself was correct.

The Phase 2 taxonomy makes the visual contract explicit. Specialists SHOULD
populate ``finding.visual_evidence`` directly (see schema/finding-v1.json);
legacy emissions and any specialist that doesn't yet populate it run through
``derive_visual_evidence()`` below, which inspects the existing match_method
+ baton_index + proposed_anchor and assigns the closest type + confidence.

Five types:

- ``exact_element`` — tight selector matching the specific DOM element the
  finding is about (renderer draws a solid rect)
- ``proxy_element`` — a real baton element near the subject but not exactly
  it (renderer draws a dashed rect)
- ``generated_expected_zone`` — a ghost/dashed overlay showing where the
  missing UI SHOULD appear; renderer draws a placeholder shape using the
  expected_overlay.template_id registry
- ``section_absence`` — section-level marker for absences without a single
  anchor (renderer draws a pill at the section centroid)
- ``page_level`` — banner spanning the page header (e.g., "DOM was edited
  during capture")

Four confidence levels:

- ``high`` — verbatim-cited element, tight rect
- ``medium`` — real element but rect may include siblings (proxy)
- ``low`` — section/viewport anchor with implicit placement
- ``needs_review`` — producer couldn't determine placement; operator must
  pick in editor.html before shipping. Phase 3 quality gates REJECT Priority
  Path and ethics findings with ``needs_review``.

See:
- ``schema/finding-v1.json`` ``visual_evidence`` property
- ``docs/ecp/2026-05-18-report-accuracy-and-hotspot-remediation-plan.md``
  Phase 2 acceptance criteria
- ``tests/test_visual_evidence.py`` derivation test cases
"""
from __future__ import annotations

from typing import Any

# Canonical mapping of match_method enum -> (visual_evidence.type, confidence)
# when the finding does NOT carry an explicit visual_evidence object.
#
# These are best-effort heuristics. A specialist that authors visual_evidence
# directly will produce richer output (e.g. observed_anchor with selector_hint
# and text_quote, or expected_overlay with template_id). The derivation here
# is the back-compat path for legacy emissions and unmigrated specialists.
_MATCH_METHOD_TO_TYPE: dict[str, tuple[str, str]] = {
    # Renderer found a tight match against a real baton element by e_index
    "e_index_lookup": ("exact_element", "high"),
    "e_index": ("exact_element", "high"),
    # Renderer fell back to section centroid because no element was cited
    "section_centroid": ("section_absence", "low"),
    # No placement signal at all — the hotspot is left blank (product.md §4.2);
    # operator places it in editor.html. Typed page_level/low (not needs_review)
    # to preserve the prior "banner" fallback's Phase-3 gate footprint: it
    # counts toward proxy_overload but does not auto-trip the priority-path
    # needs_review gate. "banner" retained for back-compat with old emissions.
    "unplaced": ("page_level", "low"),
    "banner": ("page_level", "low"),
    "operator": ("page_level", "needs_review"),
}


def _derive_from_proposed_anchor(
    proposed_anchor: dict[str, Any],
) -> tuple[str, str]:
    """Map a proposed_anchor object to (type, confidence).

    Honors the discriminated union on ``kind``:
    - kind=element → proxy_element (medium); the renderer pins relative to a
      real baton element. Confidence is medium not high because the producer
      asked for "before/after/inside" placement, which leaves room for
      sibling drift.
    - kind=section → section_absence (low) for ``section-bottom-overlay``
      placement; generated_expected_zone (low) for ``after-section``
      (overlay drawn in the GAP between sections — clearly a generated
      template, not a real anchor).
    - kind=viewport → generated_expected_zone (low). Viewport anchors are
      always page-global ghost overlays (sticky bars, above-fold persistence).
    """
    kind = proposed_anchor.get("kind")
    placement = proposed_anchor.get("placement", "")

    if kind == "element":
        return ("proxy_element", "medium")
    if kind == "section":
        if placement == "after-section":
            return ("generated_expected_zone", "low")
        return ("section_absence", "low")
    if kind == "viewport":
        return ("generated_expected_zone", "low")
    # Unknown kind — punt to operator
    return ("page_level", "needs_review")


def derive_visual_evidence(
    finding: dict[str, Any] | None = None,
    *,
    match_method: str | None = None,
    baton_index: str | None = None,
    proposed_anchor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a visual_evidence dict for a finding.

    Two calling conventions:

    1. **Pass a full finding dict** as the positional arg; the helper reads
       its own match_method, baton_index, and proposed_anchor.
    2. **Pass individual fields** as kwargs; convenient for renderer code
       paths that have these fields decomposed.

    If the finding already carries a ``visual_evidence`` object, return it
    unchanged (producer always wins; the helper only back-fills absences).

    Priority rules:

    1. Explicit ``finding.visual_evidence`` — pass through.
    2. ``match_method`` in the canonical enum — use _MATCH_METHOD_TO_TYPE.
    3. ``baton_index == "absent"`` with a ``proposed_anchor`` — derive from
       the proposed_anchor's kind + placement.
    4. ``baton_index`` is a real ``eN`` ref — exact_element (high).
    5. Nothing else known — page_level (needs_review).

    Returns a dict with at minimum ``type`` and ``confidence``; ``reason``
    is populated with a short trace of which rule fired so debug surfaces
    can show the derivation path.
    """
    if finding is not None:
        # Producer-authored visual_evidence always wins
        ve = finding.get("visual_evidence")
        if isinstance(ve, dict) and ve.get("type") and ve.get("confidence"):
            return ve

        if match_method is None:
            match_method = finding.get("match_method")
        if baton_index is None:
            # Findings flow through the pipeline in two shapes:
            #   1. Raw specialist emission: element is a dict {baton_index, ...}
            #   2. Loader-rendered: element is a string (display text), and
            #      baton_index lives at the top level
            # Try top-level first (loader shape), then fall back to nested
            # (raw shape). Tolerate either without raising.
            baton_index = finding.get("baton_index")
            if baton_index is None:
                element = finding.get("element")
                if isinstance(element, dict):
                    baton_index = element.get("baton_index")
        if proposed_anchor is None:
            proposed_anchor = finding.get("proposed_anchor")

    # Rule 2: explicit match_method enum hit
    if match_method and match_method in _MATCH_METHOD_TO_TYPE:
        ve_type, confidence = _MATCH_METHOD_TO_TYPE[match_method]
        return {
            "type": ve_type,
            "confidence": confidence,
            "reason": f"Derived from match_method={match_method}",
        }

    # Rule 3: absent + proposed_anchor → discriminated union mapping
    if baton_index == "absent" and isinstance(proposed_anchor, dict):
        ve_type, confidence = _derive_from_proposed_anchor(proposed_anchor)
        kind = proposed_anchor.get("kind", "?")
        placement = proposed_anchor.get("placement", "?")
        return {
            "type": ve_type,
            "confidence": confidence,
            "reason": (
                f"Derived from proposed_anchor.kind={kind}, "
                f"placement={placement} (baton_index=absent)"
            ),
        }

    # Rule 4: real eN reference → exact_element
    if isinstance(baton_index, str) and baton_index.startswith("e") and baton_index[1:].isdigit():
        return {
            "type": "exact_element",
            "confidence": "high",
            "reason": f"Derived from baton_index={baton_index} (no explicit visual_evidence)",
        }

    # Rule 5: insufficient signal — needs operator placement
    return {
        "type": "page_level",
        "confidence": "needs_review",
        "reason": (
            "Insufficient signal to derive visual evidence "
            "(no visual_evidence, no recognized match_method, "
            "no resolvable baton_index, no proposed_anchor). "
            "Operator should place marker in editor.html."
        ),
    }


# Used by Phase 3 quality gates and any consumer that wants to assert visual
# evidence quality without re-importing the derivation rules.
ALL_TYPES = (
    "exact_element",
    "proxy_element",
    "generated_expected_zone",
    "section_absence",
    "page_level",
)
ALL_CONFIDENCES = ("high", "medium", "low", "needs_review")


__all__ = [
    "ALL_CONFIDENCES",
    "ALL_TYPES",
    "derive_visual_evidence",
]
