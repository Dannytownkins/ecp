"""v2 hotspot resolution (Phase G deliverable 2 + 3, fix B 2026-04-30).

Replaces the v1 5-tier fuzzy resolver in ``markers.py`` with four deterministic
strategies tied to v2's baton_index + proposed_anchor contract:

    Strategy 1 — e_index_lookup (preferred)
        Finding has ``baton_index = "eN"``. Look up baton.elements[N] by
        array position. Use rect.x / rect.y / rect.width / rect.height (v2-
        format baton) OR direct x/y/width/height (v1-format baton).

    Strategy 2 — proposed_anchor dispatch (fix B, 2026-04-30)
        Finding has ``baton_index = "absent"`` AND a typed ``proposed_anchor``.
        Branch on ``proposed_anchor.kind``:

            kind=element   Look up proposed_anchor.element_baton_index in
                           baton.elements[]; pin offset by `placement`
                           (before-element / after-element /
                           inside-element-{top,center,bottom}).

            kind=section   Look up baton.sections[section_index]; pin per
                           `placement` (currently only section-bottom-overlay).

            kind=viewport  Pin at viewport-bottom-sticky position; the slide
                           picked depends on `viewport_trigger`
                           (before_first_scroll → slide 0; after_primary_-
                           cta_offscreen → first slide past slide 0).

        proposed_anchor.viewport must match the finding's device; otherwise
        the placement was authored for the wrong viewport — fall through.

    Strategy 3 — section_centroid (alias-map fallback for older findings)
        Finding has ``baton_index = "absent"`` AND no proposed_anchor AND
        ``surface`` is non-empty. Look up baton.sections[N] whose slug
        contains the surface keyword and place hotspot at the section
        centroid. Kept so older emissions that pre-date fix B keep rendering.

    Strategy 4 — unplaced (last resort, §4.2)
        Everything else: emit the finding with NO hotspot position. Below the
        auto-place confidence threshold, product.md §4.2 requires leaving the
        hotspot blank for manual placement rather than auto-placing a guess
        ("a wrong hotspot costs more than a missing one; a blank is neutral").
        The finding still ships — it is queued into the editor's manual-
        placement list (review_state marks it hotspot_confidence=
        "needs-manual-marker" with a hidden, coord-less marker) — but the
        renderer draws nothing for it. Replaces the pre-2026-05-26 "banner"
        fallback, which auto-placed a top-of-page indicator (a guess) and so
        contradicted §4.2.

This closes the §3.4 / §17.4 / §18.2.2 / §22.2 / §23.2 / §24.2 hotspot
accuracy class. With baton_index supplied directly from v2 specialist
emissions, no fuzzy CSS-selector parsing happens. proposed_anchor closes
the absent-finding placement gap without re-introducing surface-string
matching as identity (identity stays surface-based — see
scripts/assembly/business_rules.py and pipeline.py).

Markers loader merge (deliverable 3): ``merge_markers`` takes the auto-
mapped output and an operator overrides JSON. Operator entries WIN on
matching f_ref or finding_index; auto-mapped entries fill any gap.

Authored Phase G (2026-04-28); fix B added 2026-04-30 (architectural fix B
in docs/plans/2026-04-30-evening-handoff.md).
"""
from __future__ import annotations

import re
from typing import Sequence

from .geometry import (
    element_rect_css,
    element_rect_raw,
    infer_element_coord_scale,
    slide_for_css_y,
    viewport_dpr,
)


_E_INDEX_RE = re.compile(r"^e(\d+)$")

# G6 (product.md §4.2 precision-first) — an exact_element hotspot whose baton
# rect spans more than this share of the viewport is almost always anchored to a
# parent container (full header/drawer/body), not the subject element. Such
# markers are auto-down-ranked to proxy_element so they render as approximate
# (dashed) markers instead of misleading solid "exact" rects. Kept in sync with
# assembly/visual_quality.py DEFAULT_GIANT_WIDTH_PCT / DEFAULT_GIANT_HEIGHT_PCT
# (the giant_exact_rectangles gate) — tests/test_g6_oversized_downrank.py asserts
# the two stay equal, so down-ranking here makes that gate pass.
GIANT_EXACT_WIDTH_PCT = 85.0
GIANT_EXACT_HEIGHT_PCT = 70.0

# Per-kind allowed placements (mirrors schema oneOf — defensive only; the
# schema rejects mismatches at validation time).
_ELEMENT_PLACEMENTS = frozenset({
    "before-element",
    "after-element",
    "inside-element-top",
    "inside-element-center",
    "inside-element-bottom",
})
_SECTION_PLACEMENTS = frozenset({"section-bottom-overlay", "after-section"})
_VIEWPORT_PLACEMENTS = frozenset({"viewport-bottom-sticky"})

# Pixel margin (CSS px) applied before/after an element when placement is
# before-element / after-element. Small enough to keep the pin near the
# anchor; large enough to clearly read as "this thing belongs here, but
# isn't actually here" rather than overlapping the anchor itself.
_ELEMENT_PLACEMENT_MARGIN_CSS = 24.0

# Default y_pct for viewport-bottom-sticky placement. ~92% sits above the
# screenshot's bottom edge but below typical content; matches where a real
# sticky bottom bar would render.
_VIEWPORT_BOTTOM_STICKY_Y_PCT = 92.0
_VIEWPORT_BOTTOM_STICKY_X_PCT = 50.0

# Default y_pct for section-bottom-overlay. Pin sits near the bottom of the
# section's slide so it visually overlays the section without clipping.
_SECTION_BOTTOM_OVERLAY_Y_PCT = 93.0
_SECTION_BOTTOM_OVERLAY_X_PCT = 50.0


def parse_baton_index(baton_index: str | None) -> int | None:
    """Convert a baton e_index ('e5') to its 0-based array position.

    Returns None for None input or 'absent'. Returns None for malformed
    strings rather than raising — the caller falls through to the absent
    handler.
    """
    if not baton_index or baton_index == "absent":
        return None
    m = _E_INDEX_RE.match(baton_index)
    if not m:
        return None
    return int(m.group(1))


def _slide_for_y(scroll_y: float, viewport_h: float, screenshots: list) -> int:
    """Pick the slide that views ``scroll_y`` most centrally.

    Mobile section captures often overlap (slides at scrollY=2100 and
    scrollY=2360 both contain y=2486 because each slide's rendered
    height equals one full viewport, ~844px). The naive "last scrollY
    below target" picks slide 5 even though slide 4 frames the element
    closer to its visual center. We instead score every slide that
    contains the element by distance-to-viewport-center and pick the
    smallest. Falls back to nearest-slide-by-scrollY when the element
    sits above all slides or below all slides.
    """
    if not screenshots:
        return 0

    best_slide = -1
    best_distance = float("inf")
    for i, ss in enumerate(screenshots):
        if not isinstance(ss, dict):
            continue
        ss_scroll = float(ss.get("scrollY", 0) or 0)
        # Element visible on this slide if scroll_y in [ss_scroll, ss_scroll + viewport_h)
        if ss_scroll <= scroll_y < ss_scroll + viewport_h:
            relative_y = scroll_y - ss_scroll
            distance_from_center = abs(relative_y - viewport_h / 2.0)
            if distance_from_center < best_distance:
                best_distance = distance_from_center
                best_slide = i

    if best_slide >= 0:
        return best_slide

    # Fallback: element is outside every slide's viewport. Pick the
    # nearest slide by absolute scrollY distance.
    best_slide = 0
    best_distance = float("inf")
    for i, ss in enumerate(screenshots):
        if not isinstance(ss, dict):
            continue
        ss_scroll = float(ss.get("scrollY", 0) or 0)
        d = abs(ss_scroll - scroll_y)
        if d < best_distance:
            best_distance = d
            best_slide = i
    return best_slide


def _section_centroid(
    surface: str,
    sections: list,
    viewport: dict,
) -> tuple[int, float, float] | None:
    """Find the baton section matching ``surface`` and return (slide_idx, x_pct, y_pct).

    Match is case-insensitive substring on the section slug. The slide_idx
    is the section's screenshot index (or 0 fallback). x_pct / y_pct are
    percentages of natural width / height pinned to the section's vertical
    midpoint. Returns None when no section matches.
    """
    if not surface or not sections:
        return None
    needle = surface.strip().lower().replace(" ", "-")
    matched = None
    for section in sections:
        slug = (section.get("slug") or "").lower()
        if needle and (needle in slug or slug in needle):
            matched = section
            break
    if matched is None:
        return None

    # The section's screenshot_ref points to the slide; find its index.
    screenshot_ref = matched.get("screenshot_ref")
    slide_idx = 0
    # We don't have screenshots here — caller resolves screenshot_ref to slide_idx.
    # For now return the screenshot_ref so caller can map. Encode as -1 sentinel.
    # Actually return what we have and let caller map via screenshots list.

    # Y centroid = midpoint of (scroll_y_top, scroll_y_bottom) within section.
    top = float(matched.get("scroll_y_top", 0) or 0)
    bot = float(matched.get("scroll_y_bottom", 0) or 0)
    section_height = max(1.0, bot - top)
    # Use viewport height to convert section midpoint to a percent of slide height
    viewport_h = float(viewport.get("height", 1080) or 1080)
    y_pct = 50.0  # midpoint of the slide vertically — a section IS a slide chunk
    x_pct = 50.0  # center horizontally
    return (slide_idx, x_pct, y_pct, screenshot_ref)


def _resolve_element_placement(
    elem: dict,
    placement: str,
    screenshots: list,
    viewport: dict,
    element_coord_scale: float,
    sections: list | None = None,
) -> tuple[int, float, float] | None:
    """Resolve a kind=element proposed_anchor to (slide, x_pct, y_pct).

    Returns None if the element coords can't be resolved. Otherwise returns
    a slide-relative position whose y is offset per ``placement``:

        before-element        -> y just above the element top
        after-element         -> y just below the element bottom
        inside-element-top    -> y at element top
        inside-element-center -> y at element midpoint (matches the default
                                 e_index_lookup behavior, just delivered as
                                 a fallback_position so compute_marker_-
                                 positions_v2 doesn't redo rect math)
        inside-element-bottom -> y at element bottom
    """
    if not isinstance(elem, dict) or placement not in _ELEMENT_PLACEMENTS:
        return None

    viewport_h = float(viewport.get("height", 844) or 844)
    elem_y_raw = _element_y(elem)
    elem_h_raw = _element_height(elem)
    elem_y_css = elem_y_raw / element_coord_scale if element_coord_scale else elem_y_raw
    elem_h_css = elem_h_raw / element_coord_scale if element_coord_scale else elem_h_raw

    # Pick slide using the element's CENTER (matches Strategy 1 behavior so
    # tall elements don't bias to the wrong slide).
    slide_pick_y = elem_y_css + elem_h_css / 2.0
    slide = slide_for_css_y(slide_pick_y, viewport_h, screenshots, sections)
    if not screenshots or slide >= len(screenshots):
        return None

    ss = screenshots[slide] if isinstance(screenshots[slide], dict) else {}
    nat_w = float(ss.get("naturalWidth") or ss.get("width") or 1)
    nat_h = float(ss.get("naturalHeight") or ss.get("height") or 1)
    scroll_y = float(ss.get("scrollY", 0) or 0)
    if nat_w <= 0 or nat_h <= 0:
        return None

    rect_css = element_rect_css(elem, element_coord_scale) or {
        "x": 0.0,
        "width": 0.0,
    }
    ex_css = rect_css["x"]
    ew_css = rect_css["width"]

    viewport_w_css = float(viewport.get("width") or nat_w or 1)
    viewport_h_css = float(viewport.get("height") or nat_h or 1)
    sx = nat_w / max(1.0, viewport_w_css)
    sy = nat_h / max(1.0, viewport_h_css)

    # Slide-relative element box in CSS pixels.
    rel_x_css = ex_css
    rel_y_top_css = elem_y_css - scroll_y
    rel_y_bot_css = rel_y_top_css + elem_h_css

    # Apply placement to pick the y in CSS pixels relative to the slide.
    if placement == "before-element":
        rel_y_css = rel_y_top_css - _ELEMENT_PLACEMENT_MARGIN_CSS
    elif placement == "after-element":
        rel_y_css = rel_y_bot_css + _ELEMENT_PLACEMENT_MARGIN_CSS
    elif placement == "inside-element-top":
        rel_y_css = rel_y_top_css
    elif placement == "inside-element-bottom":
        rel_y_css = rel_y_bot_css
    else:  # inside-element-center
        rel_y_css = (rel_y_top_css + rel_y_bot_css) / 2.0

    # Center x at the element's horizontal midpoint.
    cx_px = (rel_x_css + ew_css / 2.0) * sx
    cy_px = rel_y_css * sy

    x_pct = max(0.0, min(100.0, (cx_px / max(1.0, nat_w)) * 100.0))
    y_pct = max(0.0, min(100.0, (cy_px / max(1.0, nat_h)) * 100.0))
    return (slide, x_pct, y_pct)


def _effective_section_bottom(
    section: dict,
    next_section: dict | None,
    page_height_px: float | None,
) -> float:
    """Defensive clamp for section.scroll_y_bottom.

    Acquirers occasionally write overlapping section ranges (capture-artifact:
    last sections share scroll positions when max-scroll caps below page height).
    The renderer must not pin a marker at a y-coordinate that physically falls
    inside the NEXT section, or the hotspot lands on the wrong screenshot.

    Effective bottom = min(scroll_y_bottom, next_section.scroll_y_top - 1, page_height_px).
    """
    raw_bot = float(section.get("scroll_y_bottom", 0) or 0)
    candidates = [raw_bot]
    if next_section is not None:
        next_top = float(next_section.get("scroll_y_top", 0) or 0)
        if next_top > 0:
            candidates.append(next_top - 1.0)
    if page_height_px is not None and page_height_px > 0:
        candidates.append(float(page_height_px))
    return min(candidates) if candidates else raw_bot


def _resolve_section_placement(
    section: dict,
    placement: str,
    screenshot_ref_to_idx: dict,
    *,
    sections: list | None = None,
    section_idx: int | None = None,
    screenshots: list | None = None,
    viewport: dict | None = None,
    page_height_px: float | None = None,
) -> tuple[int, float, float] | None:
    """Resolve a kind=section proposed_anchor to (slide, x_pct, y_pct).

    Supports two placements:

    - ``section-bottom-overlay`` — pin INSIDE the section, near its bottom edge.
      y_pct is computed from the effective section bottom (clamped against the
      next section's top + page height) relative to the SELECTED slide, NOT a
      hardcoded 93%. Closes the awdmods.com 2026-05-01 class where the hardcoded
      constant placed every section overlay at the same vertical position
      regardless of geometry.

    - ``after-section`` — pin AFTER the section ends (Phase M, 2026-05-01). Use
      when the finding describes content that belongs *after* this section
      visually completes — e.g., "trust strip below the featured collection."
      Distinct from ``section-bottom-overlay`` which means "inside the section
      near its bottom." The two were conflated in v1.

    Returns None if the section's screenshot_ref doesn't map to a known slide.
    """
    if not isinstance(section, dict) or placement not in _SECTION_PLACEMENTS:
        return None
    screenshot_ref = section.get("screenshot_ref") or ""
    slide = screenshot_ref_to_idx.get(screenshot_ref)

    # Defensive: when sections are available, compute the placement target y in page coords,
    # then re-pick the slide via _slide_for_y so an overlapping baton can't put the marker
    # on the wrong screenshot.
    target_y_page: float | None = None
    next_section: dict | None = None
    if sections is not None and section_idx is not None and 0 <= section_idx < len(sections):
        next_section = sections[section_idx + 1] if section_idx + 1 < len(sections) else None
        eff_bot = _effective_section_bottom(section, next_section, page_height_px)
        section_top = float(section.get("scroll_y_top", 0) or 0)
        if placement == "section-bottom-overlay":
            # Pin inside the section, near its effective bottom (≈90% down the section).
            target_y_page = section_top + (eff_bot - section_top) * 0.90
        elif placement == "after-section":
            # Pin just after the section ends — at next_section.top - small margin,
            # or 24px past the section's effective bottom if no next section.
            if next_section is not None:
                next_top = float(next_section.get("scroll_y_top", 0) or 0)
                target_y_page = next_top - 12.0  # just inside the next section's top
            else:
                target_y_page = eff_bot + 12.0

    # If we have enough context, re-pick the slide and compute slide-relative y_pct.
    if (
        target_y_page is not None
        and screenshots is not None
        and viewport is not None
    ):
        viewport_h = float(viewport.get("height", 844) or 844)
        slide = slide_for_css_y(target_y_page, viewport_h, screenshots, sections)
        if 0 <= slide < len(screenshots):
            ss = screenshots[slide]
            ss_scroll = float(ss.get("scrollY", 0) or 0)
            relative_y = max(0.0, target_y_page - ss_scroll)
            y_pct = max(0.0, min(100.0, (relative_y / viewport_h) * 100.0))
            return (slide, _SECTION_BOTTOM_OVERLAY_X_PCT, y_pct)

    # Fallback to the legacy behavior when context isn't passed (older callers
    # that haven't updated to the new signature).
    if slide is None:
        return None
    return (slide, _SECTION_BOTTOM_OVERLAY_X_PCT, _SECTION_BOTTOM_OVERLAY_Y_PCT)


def _resolve_viewport_placement(
    viewport_trigger: str,
    placement: str,
    screenshots: list,
) -> tuple[int, float, float] | None:
    """Resolve a kind=viewport proposed_anchor to (slide, x_pct, y_pct).

    Placement is currently only ``viewport-bottom-sticky``. The slide is
    picked from ``viewport_trigger``:

        before_first_scroll              -> slide 0 (first capture)
        after_primary_cta_offscreen      -> slide 1 if it exists, else 0

    The after_primary_cta_offscreen heuristic intentionally stays simple in
    v1 — a richer rule (find the first slide past the primary CTA's scrollY)
    can land later when a real engagement needs it.
    """
    if placement not in _VIEWPORT_PLACEMENTS:
        return None
    if not screenshots:
        slide = 0
    elif viewport_trigger == "before_first_scroll":
        slide = 0
    elif viewport_trigger == "after_primary_cta_offscreen":
        slide = 1 if len(screenshots) > 1 else 0
    else:
        return None
    return (slide, _VIEWPORT_BOTTOM_STICKY_X_PCT, _VIEWPORT_BOTTOM_STICKY_Y_PCT)


def _resolve_proposed_anchor(
    finding: dict,
    elements: list,
    sections: list,
    screenshots: list,
    viewport: dict,
    element_coord_scale: float,
    screenshot_ref_to_idx: dict,
    *,
    page_height_px: float | None = None,
) -> tuple[int, float, float, str, str] | None:
    """Strategy 2 entry point: dispatch on proposed_anchor.kind.

    Returns (slide, x_pct, y_pct, match_method, fallback_role) on success.
    Returns None when the proposed_anchor is missing, malformed, or refers
    to an out-of-range index — the caller falls through to Strategy 3.
    """
    pa = finding.get("proposed_anchor")
    if not isinstance(pa, dict):
        return None

    kind = pa.get("kind") or ""
    placement = pa.get("placement") or ""
    if not kind or not placement:
        return None

    # Viewport-mismatch guard: a mobile-device finding with a desktop-viewport
    # proposed_anchor should NOT render at the desktop placement on the mobile
    # slide. Specs say cross-device behaviors emit two findings. Defensive
    # fall-through preserves safety for hand-authored test data.
    pa_viewport = (pa.get("viewport") or "").lower()
    finding_device = (finding.get("device") or "").lower()
    if pa_viewport and finding_device and pa_viewport != finding_device:
        return None

    if kind == "element":
        idx_str = pa.get("element_baton_index") or ""
        elem_idx = parse_baton_index(idx_str)
        if elem_idx is None or elem_idx < 0 or elem_idx >= len(elements):
            return None
        resolved = _resolve_element_placement(
            elements[elem_idx],
            placement,
            screenshots,
            viewport,
            element_coord_scale,
            sections,
        )
        if resolved is None:
            return None
        slide, x_pct, y_pct = resolved
        return (slide, x_pct, y_pct, "proposed_anchor_element", "absent_near_element")

    if kind == "section":
        section_index = pa.get("section_index")
        if not isinstance(section_index, int) or section_index < 0 or section_index >= len(sections):
            return None
        # Pass full context so the resolver can clamp against next section + page height
        # (defends against acquirer-emitted overlapping section ranges) and compute
        # y_pct dynamically from real geometry rather than a hardcoded constant.
        # page_height_px is sourced by the caller from baton.capture_state.page_height_px,
        # NOT viewport — the schema places it under capture_state. Closes Codex P1
        # (page-height clamp wiring bug 2026-05-01).
        resolved = _resolve_section_placement(
            sections[section_index],
            placement,
            screenshot_ref_to_idx,
            sections=sections,
            section_idx=section_index,
            screenshots=screenshots,
            viewport=viewport,
            page_height_px=page_height_px,
        )
        if resolved is None:
            return None
        slide, x_pct, y_pct = resolved
        return (slide, x_pct, y_pct, "proposed_anchor_section", "absent_in_section")

    if kind == "viewport":
        viewport_trigger = pa.get("viewport_trigger") or ""
        resolved = _resolve_viewport_placement(viewport_trigger, placement, screenshots)
        if resolved is None:
            return None
        slide, x_pct, y_pct = resolved
        return (slide, x_pct, y_pct, "proposed_anchor_viewport", "absent_viewport_global")

    return None


def auto_map_markers_v2(
    findings: Sequence[dict],
    baton: dict,
) -> list[dict]:
    """Build the per-finding marker mapping using v2's three-strategy resolver.

    Returns a list of mapping dicts compatible with v1's
    compute_marker_positions, plus an extra 'match_method' value for
    diagnostics:

        e_index_lookup    Strategy 1 succeeded — baton_index resolves to a
                          baton element with rect coords.
        section_centroid  Strategy 3 — absent baton_index, surface matched
                          a baton section, hotspot at section midpoint.
        unplaced          Strategy 4 — no usable placement signal; emitted
                          with NO position (fallback_position=None) so the
                          renderer leaves it blank and the editor queues it
                          for manual placement (product.md §4.2).

    Every finding still gets a mapping entry, but ``unplaced`` entries carry
    no position — compute_marker_positions_v2 deliberately renders nothing
    for them, and review_state surfaces them in the manual-placement queue.
    """
    elements = baton.get("elements", [])
    sections = baton.get("sections", [])
    screenshots = baton.get("screenshots", [])
    viewport = baton.get("viewport", {})
    viewport_h = float(viewport.get("height", 844) or 844)
    # Phase M (2026-05-01) — page_height_px lives at baton.capture_state.page_height_px
    # per schema/baton-v1.json. Used by _resolve_section_placement to clamp
    # malformed last-section ranges to actual page height. Closes Codex P1.
    capture_state = baton.get("capture_state") or {}
    page_height_px: float | None = None
    if isinstance(capture_state, dict):
        raw_ph = capture_state.get("page_height_px")
        if isinstance(raw_ph, (int, float)) and raw_ph > 0:
            page_height_px = float(raw_ph)
    dpr = viewport_dpr(viewport)
    # Mobile baton stores element coords in DEVICE pixels (DPR-multiplied);
    # desktop stores CSS pixels. The v1 helper infers which scheme the baton
    # uses by comparing element extents against screenshot scrollY + viewport
    # envelope. Returns 1.0 for CSS px (passthrough) or dpr for device px.
    element_coord_scale = infer_element_coord_scale(elements, screenshots, viewport, dpr, sections)

    # Build screenshot_ref → slide_idx map for section-centroid resolution.
    screenshot_ref_to_idx: dict[str, int] = {}
    for i, ss in enumerate(screenshots):
        if isinstance(ss, dict):
            ref = ss.get("path") or ss.get("file") or ""
            if ref:
                screenshot_ref_to_idx[ref] = i

    mappings: list[dict] = []
    for f in findings:
        finding_idx = f.get("index")
        f_ref = f.get("f_ref")
        baton_index_str = f.get("baton_index")
        scope = f.get("scope") or "device"
        surface = f.get("surface") or f.get("section") or ""
        severity = (f.get("priority") or "MEDIUM").lower()
        burn_number = f.get("cluster_index") or finding_idx

        # Strategy 1: e_index lookup
        elem_idx = parse_baton_index(baton_index_str)
        if elem_idx is not None and 0 <= elem_idx < len(elements):
            elem = elements[elem_idx]
            # Find the slide this element sits on. v1 baton: element.y is
            # absolute scroll_y. v2 baton: element.rect.y is absolute scroll_y.
            # Normalize element y to CSS pixels before slide selection.
            elem_y_raw = _element_y(elem)
            elem_y_css = elem_y_raw / element_coord_scale if element_coord_scale else elem_y_raw
            # Tall elements (footer, hero, full-page gallery) span multiple
            # slides. Using the TOP y biases slide selection toward the slide
            # ending at the element's start — e.g. a footer starting at the
            # exact scrollY of slide N+1 gets pinned on slide N because
            # element.top sits near slide N's viewport center. Use the
            # element CENTER for slide picking; coordinate math downstream
            # still uses element.top via _compute_marker_positions_v2.
            elem_h_raw = _element_height(elem)
            elem_h_css = elem_h_raw / element_coord_scale if element_coord_scale else elem_h_raw
            # Bug A/B fix (2026-05-02): an element with no usable rect
            # silently pinned to slide-0 top-left under the old code, and
            # match_method continued to advertise "e_index_lookup" — i.e.
            # hotspot_confidence lied about placement quality. Detect both
            # the no-geometry case and the off-slide case (element y past
            # the captured screenshot envelope, common when the page is
            # taller than the screenshot run) and downgrade match_method
            # so review_state._hotspot_confidence maps to fallback-absence
            # — surfacing the finding for manual placement in the editor.
            if elem_y_raw <= 0 and elem_h_raw <= 0:
                # No geometry at all. Fall through to Strategy 2/3/4.
                pass
            else:
                slide_pick_y = elem_y_css + elem_h_css / 2.0
                slide = slide_for_css_y(slide_pick_y, viewport_h, screenshots, sections)
                degenerate = False
                if 0 <= slide < len(screenshots):
                    ss = screenshots[slide] if isinstance(screenshots[slide], dict) else {}
                    ss_scroll = float(ss.get("scrollY", 0) or 0)
                    if not (ss_scroll <= slide_pick_y < ss_scroll + viewport_h):
                        degenerate = True
                method = "e_index_lookup_offslide" if degenerate else "e_index_lookup"
                fallback_role = "absent_offslide_element" if degenerate else None
                mappings.append({
                    "finding_index": finding_idx,
                    "f_ref": f_ref,
                    "burn_number": burn_number,
                    "baton_element_index": elem_idx,
                    "slide": slide,
                    "match_method": method,
                    "severity": severity,
                    "fallback_role": fallback_role,
                    "fallback_position": None,
                    "scope": scope,
                })
                continue

        # Strategy 2: proposed_anchor dispatch (fix B, 2026-04-30).
        # Absent findings emitted with a typed proposed_anchor get pinned per
        # the discriminator; falls through to Strategy 3 only when the anchor
        # is missing, malformed, or its viewport doesn't match this device.
        proposed = _resolve_proposed_anchor(
            f, elements, sections, screenshots, viewport,
            element_coord_scale, screenshot_ref_to_idx,
            page_height_px=page_height_px,
        )
        if proposed is not None:
            slide, x_pct, y_pct, match_method, fallback_role = proposed
            mappings.append({
                "finding_index": finding_idx,
                "f_ref": f_ref,
                "burn_number": burn_number,
                "baton_element_index": None,
                "slide": slide,
                "match_method": match_method,
                "severity": severity,
                "fallback_role": fallback_role,
                "fallback_position": {"x_pct": x_pct, "y_pct": y_pct},
                "scope": scope,
            })
            continue

        # Strategy 3: section centroid alias-map fallback (older absent
        # findings that pre-date proposed_anchor; surface-string match against
        # baton.sections[].slug).
        if surface:
            centroid = _section_centroid(surface, sections, viewport)
            if centroid is not None:
                _, x_pct, y_pct, screenshot_ref = centroid
                slide = screenshot_ref_to_idx.get(screenshot_ref or "", 0)
                mappings.append({
                    "finding_index": finding_idx,
                    "f_ref": f_ref,
                    "burn_number": burn_number,
                    "baton_element_index": None,
                    "slide": slide,
                    "match_method": "section_centroid",
                    "severity": severity,
                    "fallback_role": "absent_in_section",
                    "fallback_position": {"x_pct": x_pct, "y_pct": y_pct},
                    "scope": scope,
                })
                continue

        # Strategy 4: unplaced (last resort) — product.md §4.2.
        # No placement signal resolved (no e_index geometry, no usable
        # proposed_anchor, no surface section match). The spec is explicit:
        # below the auto-place confidence threshold, LEAVE IT BLANK for manual
        # placement — never auto-place a guess. So we emit the finding with no
        # fallback_position; compute_marker_positions_v2 renders nothing, and
        # review_state queues it for manual placement (hotspot_confidence=
        # "needs-manual-marker"). slide=0 is a nominal anchor only so the
        # review-state marker has a valid slide_id; no marker is drawn there.
        mappings.append({
            "finding_index": finding_idx,
            "f_ref": f_ref,
            "burn_number": burn_number,
            "baton_element_index": None,
            "slide": 0,
            "match_method": "unplaced",
            "severity": severity,
            "fallback_role": "absent_unplaced",
            "fallback_position": None,
            "scope": scope,
        })

    # Phase 2 — augment each mapping with visual_evidence so downstream
    # consumers (review-state writer, HTML builder, Phase 3 quality gates)
    # have a stable typed contract instead of having to interpret
    # match_method strings. Source priority: producer-authored
    # finding.visual_evidence > derived from match_method/proposed_anchor.
    # See scripts/report/visual_evidence.py for the derivation rules.
    from .visual_evidence import derive_visual_evidence
    findings_by_index: dict[int, dict] = {
        f.get("index"): f for f in findings if f.get("index") is not None
    }
    for m in mappings:
        f = findings_by_index.get(m.get("finding_index"))
        if f is None:
            m["visual_evidence"] = derive_visual_evidence(
                match_method=m.get("match_method"),
                baton_index=None,
                proposed_anchor=None,
            )
            continue
        m["visual_evidence"] = derive_visual_evidence(
            f,
            match_method=m.get("match_method"),
        )
        # G6: down-rank an oversized exact_element marker to an approximate
        # proxy_element (renders dashed) so it stops claiming pixel-precise
        # placement it doesn't have, and the giant_exact_rectangles gate passes.
        _downrank_oversized_exact(m, elements, viewport, element_coord_scale)

    return mappings


def _downrank_oversized_exact(
    mapping: dict,
    elements: list,
    viewport: dict,
    element_coord_scale: float,
) -> None:
    """Down-rank an exact_element mapping to proxy_element when its baton rect is
    giant (product.md §4.2 precision-first). Mutates ``mapping['visual_evidence']``
    in place; no-op for non-exact types or normally-sized elements.

    The size test uses element-width-as-percent-of-viewport, which equals the
    slide-relative zone w/h pct the renderer computes (zone.w_pct =
    element_width_css / viewport_width_css * 100), so the threshold here matches
    exactly what the giant_exact_rectangles gate measures on the rendered marker.
    """
    ve = mapping.get("visual_evidence") or {}
    if ve.get("type") != "exact_element":
        return
    eidx = mapping.get("baton_element_index")
    if not isinstance(eidx, int) or eidx < 0 or eidx >= len(elements):
        return
    rect = element_rect_css(elements[eidx], element_coord_scale)
    if not rect:
        return
    try:
        vw = float(viewport.get("width") or 0)
        vh = float(viewport.get("height") or 0)
    except (TypeError, ValueError):
        return
    if vw <= 0 or vh <= 0:
        return
    w_pct = rect["width"] / vw * 100.0
    h_pct = rect["height"] / vh * 100.0
    if w_pct > GIANT_EXACT_WIDTH_PCT or h_pct > GIANT_EXACT_HEIGHT_PCT:
        mapping["visual_evidence"] = {
            "type": "proxy_element",
            "confidence": "low",
            "reason": (
                f"Auto-down-ranked from exact_element: baton rect is "
                f"{w_pct:.0f}%w/{h_pct:.0f}%h of the viewport (> "
                f"{GIANT_EXACT_WIDTH_PCT:.0f}%w/{GIANT_EXACT_HEIGHT_PCT:.0f}%h) — "
                f"likely a parent container, not the subject element "
                f"(product.md §4.2 precision-first)."
            ),
        }


def _element_y(elem: dict) -> float:
    """Return absolute scroll_y of an element, accommodating both v1 and v2 baton shapes."""
    rect = element_rect_raw(elem)
    return rect["y"] if rect else 0.0


def _element_height(elem: dict) -> float:
    """Return element height (CSS px), 0 when unavailable."""
    rect = element_rect_raw(elem)
    return rect["height"] if rect else 0.0


def merge_markers(
    auto_mapped: list[dict],
    operator_overrides: list[dict] | None,
) -> list[dict]:
    """Merge operator-supplied overrides with the auto-mapped result.

    Operator entries win on matching ``f_ref`` (preferred v2 key) or
    ``finding_index`` (v1 fallback). Auto-mapped entries fill any gap. v1
    behavior was REPLACE — operator file overrode the whole list. v2
    behavior is MERGE so an operator pinning two findings doesn't accidentally
    drop the auto-mapping for the other 40+ findings.

    Closes Phase G deliverable 3. Resolves §23.3 #3 / §24.5 #2.
    """
    if not operator_overrides:
        return list(auto_mapped)

    by_key: dict = {}  # key = (f_ref or finding_index)
    for m in auto_mapped:
        key = m.get("f_ref") or ("idx", m.get("finding_index"))
        by_key[key] = dict(m)

    for ov in operator_overrides:
        key = ov.get("f_ref") or ("idx", ov.get("finding_index"))
        # Operator wins; preserve any auto-mapped fields the override didn't set.
        if key in by_key:
            merged = dict(by_key[key])
            merged.update(ov)
            merged["match_method"] = "operator_override"
            by_key[key] = merged
        else:
            entry = dict(ov)
            entry.setdefault("match_method", "operator_override")
            by_key[key] = entry

    # Preserve original auto_mapped order for stability; append operator-only
    # entries at the end.
    out: list[dict] = []
    seen: set = set()
    for m in auto_mapped:
        key = m.get("f_ref") or ("idx", m.get("finding_index"))
        if key in by_key and key not in seen:
            out.append(by_key[key])
            seen.add(key)
    for ov in operator_overrides:
        key = ov.get("f_ref") or ("idx", ov.get("finding_index"))
        if key not in seen:
            out.append(by_key[key])
            seen.add(key)
    return out


def compute_marker_positions_v2(
    markers_mapping: list[dict],
    baton: dict,
) -> dict:
    """Compute pixel positions for v2 markers on screenshots.

    Mirrors v1's compute_marker_positions semantics so the rest of the
    renderer pipeline (hotspot overlays, click handlers) doesn't need to
    change. Difference from v1: handles both element.rect.{x,y,...} (v2
    baton) and element.{x,y,...} (v1 baton) shapes.
    """
    elements = baton.get("elements", [])
    screenshots = baton.get("screenshots", [])
    viewport = baton.get("viewport", {})
    dpr = viewport_dpr(viewport)
    element_coord_scale = infer_element_coord_scale(
        elements,
        screenshots,
        viewport,
        dpr,
        baton.get("sections") or [],
    )

    # Default natural dimensions per device per contracts/device-semantics.md.
    _DEVICE_FALLBACKS = {
        "mobile": (390, 844, 3),
        "laptop": (1440, 900, 1),
        "desktop": (1920, 1080, 1),
    }
    device = (baton.get("device") or "laptop").lower()
    _fw, _fh, _fdpr = _DEVICE_FALLBACKS.get(device, _DEVICE_FALLBACKS["laptop"])
    try:
        default_nat_w = int(viewport.get("width") or _fw)
    except (ValueError, TypeError):
        default_nat_w = _fw
    try:
        default_nat_h = int(viewport.get("height") or _fh)
    except (ValueError, TypeError):
        default_nat_h = _fh

    slide_markers: dict = {}
    for mapping in markers_mapping:
        slide = mapping.get("slide")
        if slide is None:
            continue
        if slide not in slide_markers:
            slide_markers[slide] = []

        finding_idx = mapping["finding_index"]
        burn_number = mapping.get("burn_number") or finding_idx
        severity = mapping.get("severity", "medium")
        elem_idx = mapping.get("baton_element_index")
        fallback_pos = mapping.get("fallback_position")

        # Slide natural dimensions
        if isinstance(screenshots, list) and slide < len(screenshots):
            ss = screenshots[slide] if isinstance(screenshots[slide], dict) else {}
            nat_h = int(ss.get("naturalHeight") or ss.get("height") or default_nat_h)
            nat_w = int(ss.get("naturalWidth") or ss.get("width") or default_nat_w)
            scroll_y = float(ss.get("scrollY", 0) or 0)
        else:
            ss = {}
            nat_h = default_nat_h
            nat_w = default_nat_w
            scroll_y = 0.0

        if fallback_pos is not None:
            cx = int(nat_w * fallback_pos["x_pct"] / 100)
            cy = int(nat_h * fallback_pos["y_pct"] / 100)
            slide_markers[slide].append({
                "number": burn_number,
                "finding_index": finding_idx,
                "f_ref": mapping.get("f_ref"),
                "x": cx,
                "y": cy,
                "x_pct": fallback_pos["x_pct"],
                "y_pct": fallback_pos["y_pct"],
                "severity": severity,
                "fallback_role": mapping.get("fallback_role"),
                "match_method": mapping.get("match_method"),
                "visual_evidence": mapping.get("visual_evidence"),
            })
            continue

        if elem_idx is None or elem_idx >= len(elements):
            continue

        elem = elements[elem_idx]
        rect_css = element_rect_css(elem, element_coord_scale) or {
            "x": 0.0,
            "y": 0.0,
            "width": 0.0,
            "height": 0.0,
        }
        ex = rect_css["x"]
        ey = rect_css["y"]
        ew = rect_css["width"]
        eh = rect_css["height"]

        # Convert absolute coords to slide-relative coords.
        # Element y is absolute scroll_y from page top. Slide.scrollY is the
        # scroll position when the slide's screenshot was captured. So slide-
        # relative y = elem_y - scroll_y, then scaled to natural dimensions.
        try:
            viewport_w_css = float(viewport.get("width") or nat_w or 1)
        except (TypeError, ValueError):
            viewport_w_css = float(nat_w or 1)
        try:
            viewport_h_css = float(viewport.get("height") or nat_h or 1)
        except (TypeError, ValueError):
            viewport_h_css = float(nat_h or 1)

        sx = float(nat_w) / max(1.0, viewport_w_css)
        sy = float(nat_h) / max(1.0, viewport_h_css)

        # Relative to slide
        rel_x_css = ex
        rel_y_css = ey - scroll_y

        cx = int(rel_x_css * sx + (ew * sx) / 2)
        cy = int(rel_y_css * sy + (eh * sy) / 2)

        # Clamp inside slide bounds — defensive.
        cx = max(0, min(cx, nat_w))
        cy = max(0, min(cy, nat_h))

        x_pct = (cx / max(1, nat_w)) * 100
        y_pct = (cy / max(1, nat_h)) * 100

        # Build zone (percentages) for rectangle hotspot overlays. The
        # renderer's build_hotspot_overlays_html reads m["zone"] with
        # left_pct/top_pct/w_pct/h_pct; falls through to circle when zone
        # is missing or too small. Phase G deliverable: precise element
        # rectangles instead of circle markers (Dan's Operator Checkpoint
        # #4 feedback — rectangles outline the element directly, like the
        # v1 baseline's red-outlined searchbar shot).
        rect_left_pct = (rel_x_css * sx) / max(1, nat_w) * 100
        rect_top_pct = (rel_y_css * sy) / max(1, nat_h) * 100
        rect_w_pct = (ew * sx) / max(1, nat_w) * 100
        rect_h_pct = (eh * sy) / max(1, nat_h) * 100
        # Clamp inside slide bounds and require minimum visible size.
        rect_left_pct = max(0.0, min(rect_left_pct, 100.0))
        rect_top_pct = max(0.0, min(rect_top_pct, 100.0))
        rect_w_pct = max(0.0, min(rect_w_pct, 100.0 - rect_left_pct))
        rect_h_pct = max(0.0, min(rect_h_pct, 100.0 - rect_top_pct))

        zone = None
        if rect_w_pct >= 2.0 and rect_h_pct >= 2.0:
            zone = {
                "left_pct": rect_left_pct,
                "top_pct": rect_top_pct,
                "w_pct": rect_w_pct,
                "h_pct": rect_h_pct,
            }

        slide_markers[slide].append({
            "number": burn_number,
            "finding_index": finding_idx,
            "f_ref": mapping.get("f_ref"),
            "x": cx,
            "y": cy,
            "x_pct": x_pct,
            "y_pct": y_pct,
            "severity": severity,
            "fallback_role": None,
            "match_method": mapping.get("match_method"),
            "visual_evidence": mapping.get("visual_evidence"),
            "zone": zone,
            # Element bounding box (in slide pixels) for diagnostic / future renderers.
            "rect": {
                "x": int(rel_x_css * sx),
                "y": int(rel_y_css * sy),
                "width": int(ew * sx),
                "height": int(eh * sy),
            },
        })

    return slide_markers
