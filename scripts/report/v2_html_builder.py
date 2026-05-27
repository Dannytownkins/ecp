"""v2 HTML report orchestrator (Phase G).

Wraps the v2 input loader (``v2_loader``) and v2 marker resolver
(``v2_markers``) around the existing html_builder helpers so the rest of
the renderer pipeline (citations, screenshots, metrics, ethics, metadata,
HTML fragments, assemble_html, writer) stays unchanged.

The v1 path through ``html_builder.generate_report`` is NOT touched; v2
dispatches via the ``--v2`` flag in ``scripts/generate-report.py`` (or
auto-detection of synthesizer-emission-v1.json).

Authored Phase G (2026-04-28).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from .geometry import backfill_screenshots_from_sections
from .geometry_validator import format_validation_report, validate_v2_hotspot_geometry
from .v2_loader import load_v2_engagement
from .v2_markers import auto_map_markers_v2, compute_marker_positions_v2, merge_markers
from . import html_builder as v1
from .templates.components import assign_cluster_indices
from .templates.html_structure import assemble_html
from .utils import aspect_ratio_value, get_device_frame_css, escape_html
from .path_safety import resolve_within_base


def _build_evidence_anchors_html(finding: dict) -> str:
    """Render a per-finding evidence-anchors detail-section snippet.

    Phase G deliverable 4: surface ``evidence_anchors[].context`` and link
    visual anchors to the referenced screenshot at the captured scroll
    position so an operator can spot-check the finding's underlying signal
    during verification.

    ``evidence_anchors`` is a list of dicts with: type ("dom" | "visual" |
    "both"), reference (e_index or screenshot path), scroll_y (optional),
    viewport (optional), context (descriptive prose).

    Returns an HTML string to be appended to the per-finding detail card.
    Returns "" if the finding has no anchors so the caller can no-op.
    """
    anchors = finding.get("evidence_anchors") or []
    if not anchors:
        return ""

    items: list[str] = []
    for ea in anchors:
        atype = (ea.get("type") or "").lower()
        ref = ea.get("reference") or ""
        scroll_y = ea.get("scroll_y")
        viewport = ea.get("viewport") or ""
        context = ea.get("context") or ""

        # Build a compact label: "DOM e5", "Visual section-1.jpg @ y=403", etc.
        if atype == "dom":
            label = f"DOM &middot; <code>{escape_html(ref)}</code>"
        elif atype == "visual":
            scroll_part = f" @ y={int(scroll_y)}" if scroll_y is not None else ""
            viewport_part = f" ({escape_html(viewport)})" if viewport else ""
            label = f"Visual &middot; <code>{escape_html(ref)}</code>{escape_html(scroll_part)}{viewport_part}"
        elif atype == "both":
            scroll_part = f" @ y={int(scroll_y)}" if scroll_y is not None else ""
            label = f"DOM + Visual &middot; <code>{escape_html(ref)}</code>{escape_html(scroll_part)}"
        else:
            label = f"{escape_html(atype.upper())} &middot; <code>{escape_html(ref)}</code>"

        # Visual references are screenshot files in the engagement dir; we
        # can't link to them from inside the embedded HTML (screenshots are
        # base64 inline), but we can mark them visually so an operator
        # opening the HTML next to the engagement dir can cross-reference.
        ctx_html = f'<div class="evidence-anchor-context">{escape_html(context)}</div>' if context else ""

        items.append(
            '<li class="evidence-anchor-item">'
            f'<div class="evidence-anchor-label">{label}</div>'
            f'{ctx_html}'
            '</li>'
        )

    return (
        '<div class="detail-section">'
        '<h4>Evidence anchors</h4>'
        f'<ul class="evidence-anchors-list">{"".join(items)}</ul>'
        '</div>'
    )


def _load_operator_overrides(markers_file: str | None) -> list[dict] | None:
    """Read an operator markers JSON. Returns None when no file or invalid."""
    if not markers_file:
        return None
    try:
        with open(markers_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, IOError, json.JSONDecodeError):
        return None
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("markers"), list):
        return data["markers"]
    return None


def generate_v2_report(
    engagement_dir: str | Path,
    device: str,
    plugin_root: str | Path,
    audit_file: str | None = None,
    baton_file: str | None = None,
    markers_file: str | None = None,
    output_file: str | None = None,
    review_state_file: str | Path | None = None,
) -> Path:
    """Generate the v2 visual report HTML.

    v2 input contract (read from engagement_dir):
    - audit-{device}.md (synthesizer markdown audit)
    - synthesizer-emission-v1.json (priority_path + manifests)
    - cluster-{cluster}-{device}.json (per-device specialist emissions)
    - ethics-findings.json (page-scope ethics emission)
    - baton.json / baton-mobile.json (engagement baton with screenshots[])

    Optional:
    - markers JSON file with operator overrides — merged with auto-mapped
      hotspots (v1 was REPLACE, v2 is MERGE per Phase G deliverable 3).

    Output: writes visual-report{-{device}}.html into engagement_dir,
    returns the output Path.
    """
    engagement_path = Path(engagement_dir)
    plugin_path = Path(plugin_root)

    if markers_file:
        try:
            markers_file = str(resolve_within_base(markers_file, engagement_path))
        except ValueError as exc:
            print(
                f"ERROR: --markers path rejected (must live inside engagement dir): {exc}",
                file=sys.stderr,
            )
            sys.exit(2)

    audit_file = audit_file or f"audit-{device}.md"
    if baton_file is None:
        baton_file = "baton.json" if device == "desktop" else f"baton-{device}.json"

    # Phase 1: Load inputs via v2_loader
    inputs = load_v2_engagement(
        engagement_path, device, plugin_path,
        audit_file=audit_file, baton_file=baton_file,
    )

    review_state = _load_review_state(review_state_file, engagement_path)

    # Phase 2: Resolve citations (mutates findings in place; reuses v1 helper).
    v1._resolve_citations(
        inputs["findings"],
        plugin_path,
        page_url=inputs.get("page_url"),
    )

    if review_state:
        _apply_review_state_to_findings(inputs["findings"], review_state)
        inputs["findings"] = [f for f in inputs["findings"] if not f.get("_review_hidden")]

    # Phase 2b: Cluster-scoped F-NN + fid for the JS runtime hotspot binding.
    # The renderer builds an internal fid (cluster + 1-based-cluster-index)
    # for hotspot click → detail panel routing. v2's canonical f_ref is what
    # the JSON cites; cluster_index keeps backwards compat with the existing
    # JS runtime.
    assign_cluster_indices(inputs["findings"])

    # Phase 2c: Pre-render evidence_anchors HTML snippets onto each finding
    # so the v1 build_detail_panels_html template can include them when
    # present (Phase G deliverable 4). v1 findings won't have anchors;
    # snippet is empty string and the section is skipped.
    for f in inputs["findings"]:
        f["evidence_anchors_html"] = _build_evidence_anchors_html(f)

    # Phase 3a: Backfill ``baton.screenshots[]`` from ``sections[]`` BEFORE
    # marker mapping. v2 batons use ``sections[].screenshot_ref``; v1 helpers
    # (used by both ``auto_map_markers_v2`` slide-resolution and
    # ``_infer_element_coord_scale`` DPR detection) read ``baton.screenshots[]``.
    # If this backfill happens AFTER mapping, all hotspots default to slide 0
    # AND mobile DPR scaling falls back to passthrough (3x-scaled element
    # coords get treated as CSS-px, causing systematic offset). Forward-compat:
    # if a baton already has both fields, the v1 array wins.
    backfill_screenshots_from_sections(inputs["baton"], engagement_path)

    # Phase 3b: v2 marker mapping with merge (auto-map + operator overrides).
    # MUST run after Phase 3a — see the comment block above for the
    # init-order bug this fixes.
    auto_mapped = auto_map_markers_v2(inputs["findings"], inputs["baton"])
    operator_overrides = _load_operator_overrides(markers_file)
    merged_mappings = merge_markers(auto_mapped, operator_overrides)
    slide_markers = compute_marker_positions_v2(merged_mappings, inputs["baton"])
    geometry_validation = validate_v2_hotspot_geometry(
        inputs["baton"],
        inputs["findings"],
        merged_mappings,
        slide_markers,
    )
    if not geometry_validation["passed"]:
        print(
            format_validation_report(
                geometry_validation,
                engagement=engagement_path,
                device=device,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1)
    if review_state:
        slide_markers = _apply_review_state_to_slide_markers(
            slide_markers,
            review_state,
            inputs["findings"],
        )

    # Phase 3c: Process screenshots (reuses v1 helper) using the populated
    # baton.screenshots[] from Phase 3a + the marker positions from Phase 3b.
    screenshots = v1._process_screenshots(
        engagement_path, inputs["baton"], slide_markers
    )

    # Phase 4: Metrics + ethics.
    metrics = v1._compute_metrics(inputs["findings"])
    has_ethics_violations = v1._check_ethics(engagement_path, audit_file, inputs["findings"])

    # Phase 5: Header metadata.
    metadata = v1._load_metadata(
        engagement_path, inputs["baton"], inputs["meta"], device, plugin_path
    )
    # Augment with v2 dispatch shape banner if degraded mode was used.
    synth_emission = inputs.get("synthesizer_emission") or {}
    if synth_emission.get("degraded_mode"):
        metadata["dispatch_shape_banner"] = (
            "Synthesizer ran in degraded (per-device) mode — scope='page' "
            "prose was assembled from Layer-2 phrasing seeds rather than a "
            "single-author synthesis pass."
        )
    else:
        metadata["dispatch_shape_banner"] = ""

    # Phase 6: HTML fragments (reuses v1 builder).
    fragments = v1._build_html_fragments(
        inputs["findings"], inputs["priority_path_stories"],
        slide_markers, metrics, has_ethics_violations, screenshots,
        inputs.get("audit_md_text", ""),
    )

    # Phase 7: Assemble context and HTML.
    has_screenshots = len(screenshots["slide_base64"]) > 0
    ctx = {
        **metadata, **metrics, **fragments,
        "plugin_version": inputs["plugin_version"],
        "device": device,
        "has_screenshots": has_screenshots,
        "slide_sources_json": json.dumps(
            [f"data:image/jpeg;base64,{b64}" for b64 in screenshots["slide_base64"]]
        ).replace("</", "<\\/"),
        "slide_aspect_ratios_json": json.dumps(screenshots["slide_aspect_ratios"]),
        "initial_slide_aspect_ratio": (
            screenshots["slide_aspect_ratios"][0]
            if screenshots["slide_aspect_ratios"]
            else screenshots["default_slide_aspect_ratio"]
        ),
        "device_frame_css": get_device_frame_css(device),
        "device_stand_html": (
            '''<div class="device-stand"></div>
        <div class="device-stand-base"></div>'''
            if device == "desktop" else ""
        ),
    }
    html = assemble_html(ctx)

    # Phase 8: Write output (reuses v1 helper).
    if not output_file:
        if device == "laptop":
            output_file = "visual-report-v2.html"
        else:
            output_file = f"visual-report-{device}-v2.html"

    output_path = engagement_path / output_file
    output_path.write_text(html, encoding="utf-8")

    # CLI summary
    mapped = sum(len(m) for m in slide_markers.values())
    e_index_count = sum(
        1 for m in merged_mappings if m.get("match_method") == "e_index_lookup"
    )
    section_count = sum(
        1 for m in merged_mappings if m.get("match_method") == "section_centroid"
    )
    banner_count = sum(
        1 for m in merged_mappings if m.get("match_method") == "banner"
    )
    unplaced_count = sum(
        1 for m in merged_mappings if m.get("match_method") == "unplaced"
    )
    op_count = sum(
        1 for m in merged_mappings if m.get("match_method") == "operator_override"
    )
    pa_element = sum(
        1 for m in merged_mappings if m.get("match_method") == "proposed_anchor_element"
    )
    pa_section = sum(
        1 for m in merged_mappings if m.get("match_method") == "proposed_anchor_section"
    )
    pa_viewport = sum(
        1 for m in merged_mappings if m.get("match_method") == "proposed_anchor_viewport"
    )

    print(f"v2 report written to: {output_path}")
    print(f"  Device: {metadata['device_label']}")
    print(f"  Findings: {metrics['total_findings']}")
    print(f"  Screenshots: {len(screenshots['slide_base64'])}")
    print(f"  Hotspots placed: {mapped}")
    print(
        f"  Match methods: e_index={e_index_count} "
        f"proposed_anchor(element={pa_element} section={pa_section} viewport={pa_viewport}) "
        f"section_centroid={section_count} unplaced={unplaced_count} banner={banner_count} "
        f"operator={op_count}"
    )

    return output_path


def _load_review_state(review_state_file: str | Path | None, engagement_path: Path) -> dict | None:
    if not review_state_file:
        return None
    review_path = Path(review_state_file)
    if not review_path.is_absolute():
        review_path = engagement_path / review_path
    try:
        with review_path.open("r", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, IOError, json.JSONDecodeError):
        return None
    return state if isinstance(state, dict) else None


def _review_ref_to_fid(f_ref: str | None) -> str | None:
    if not f_ref:
        return None
    parts = str(f_ref).rsplit(" ", 1)
    if len(parts) != 2:
        return None
    return f"{parts[0]}/{parts[1]}"


def _review_override_enabled(review_finding: dict) -> bool:
    status = (review_finding.get("status") or "").lower()
    if status in {"edited", "approved"}:
        return True
    override_keys = (
        "finding_title_override",
        "finding_body_override",
        "observation_override",
        "recommendation_override",
        "why_this_matters_override",
        "callout_title_override",
        "callout_body_override",
        "callout_position",
        "callout_color",
    )
    return any(review_finding.get(key) for key in override_keys)


def _review_effects_by_ref(review_state: dict) -> dict[str, list[dict]]:
    slide_id_to_idx = {
        slide.get("slide_id"): idx
        for idx, slide in enumerate(review_state.get("slides", []))
        if isinstance(slide, dict) and slide.get("slide_id")
    }
    hidden_refs = {
        f.get("f_ref")
        for f in review_state.get("findings", [])
        if isinstance(f, dict)
        and f.get("f_ref")
        and (f.get("status") or "").lower() == "hidden"
    }
    effects_by_ref: dict[str, list[dict]] = {}
    allowed_keys = {
        "type",
        "opacity",
        "rect",
        "mode",
        "strength_pct",
        "radius_px",
        "feather_pct",
        "hidden",
    }
    for slide_edit in review_state.get("slide_edits", []):
        if not isinstance(slide_edit, dict):
            continue
        slide_id = slide_edit.get("slide_id")
        slide_idx = slide_id_to_idx.get(slide_id)
        if slide_idx is None:
            continue
        for effect in slide_edit.get("effects", []):
            if not isinstance(effect, dict):
                continue
            ref = effect.get("f_ref")
            if not ref or ref in hidden_refs or effect.get("hidden") is True:
                continue
            effect_type = (effect.get("type") or "").lower()
            if effect_type not in {"dim", "blur"}:
                continue
            clean = {k: effect.get(k) for k in allowed_keys if k in effect}
            clean["type"] = effect_type
            clean["slide"] = slide_idx
            clean["slide_id"] = slide_id
            effects_by_ref.setdefault(ref, []).append(clean)
    return effects_by_ref


def _review_float(value, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _apply_review_state_to_findings(findings: list[dict], review_state: dict) -> None:
    review_by_ref = {
        f.get("f_ref"): f
        for f in review_state.get("findings", [])
        if isinstance(f, dict) and f.get("f_ref")
    }
    effects_by_ref = _review_effects_by_ref(review_state)
    for finding in findings:
        ref = finding.get("f_ref")
        review = review_by_ref.get(ref)
        if not review:
            continue
        status = (review.get("status") or "").lower()
        if status == "hidden":
            finding["_review_hidden"] = True
            continue
        review_effects = effects_by_ref.get(ref, [])
        if not _review_override_enabled(review) and not review_effects:
            continue

        finding["_review_status"] = status or None
        if review.get("finding_title_override"):
            finding["title"] = review["finding_title_override"]
        if review.get("observation_override"):
            finding["observation"] = review["observation_override"]
        if review.get("recommendation_override"):
            finding["recommendation"] = review["recommendation_override"]
        if review.get("why_this_matters_override"):
            finding["why_matters"] = review["why_this_matters_override"]
        if review.get("element_override"):
            finding["element"] = review["element_override"]
        if isinstance(review.get("evidence_anchors_override"), list):
            finding["evidence_anchors"] = review["evidence_anchors_override"]

        callout_title = review.get("callout_title_override") or review.get("callout_title")
        callout_body = review.get("callout_body_override") or review.get("callout_body")
        if callout_title:
            finding["review_callout_title"] = callout_title
        if callout_body:
            finding["review_callout_body"] = callout_body
        if review.get("callout_color"):
            finding["review_callout_color"] = review["callout_color"]
        if review.get("callout_position") and review.get("callout_visible", True):
            finding["review_callout_position"] = review["callout_position"]
        if review_effects:
            finding["review_effects"] = review_effects


def _apply_review_state_to_slide_markers(
    slide_markers: dict,
    review_state: dict,
    findings: list[dict],
) -> dict:
    slide_id_to_idx = {
        slide.get("slide_id"): idx
        for idx, slide in enumerate(review_state.get("slides", []))
        if isinstance(slide, dict) and slide.get("slide_id")
    }
    findings_by_ref = {f.get("f_ref"): f for f in findings if f.get("f_ref")}
    review_findings = {
        f.get("f_ref"): f
        for f in review_state.get("findings", [])
        if isinstance(f, dict) and f.get("f_ref") and _review_override_enabled(f)
    }
    active_refs = set(review_findings)
    markers_by_ref = {}
    for marker in review_state.get("markers", []):
        if not isinstance(marker, dict):
            continue
        ref = marker.get("f_ref")
        if ref not in active_refs:
            continue
        marker_id = str(marker.get("marker_id") or "")
        if marker_id.endswith("-ai"):
            continue
        markers_by_ref[ref] = marker

    if not markers_by_ref:
        return slide_markers

    patched = {}
    for slide_idx, markers in slide_markers.items():
        kept = [m for m in markers if m.get("f_ref") not in markers_by_ref]
        if kept:
            patched[slide_idx] = kept

    for ref, marker in markers_by_ref.items():
        finding = findings_by_ref.get(ref)
        if not finding:
            continue
        slide_idx = slide_id_to_idx.get(marker.get("slide_id"))
        if slide_idx is None:
            continue
        shape = marker.get("shape") or "rect"
        x = _review_float(marker.get("x_pct"), 50)
        y = _review_float(marker.get("y_pct"), 50)
        w = _review_float(marker.get("w_pct"), 0)
        h = _review_float(marker.get("h_pct"), 0)
        # Phase 3 hardening (2026-05-18) — preserve visual_evidence through
        # operator overrides so reviewed reports still emit the Phase 2
        # hotspot-ve-* CSS classes. Source priority: marker's own
        # visual_evidence (if the operator/reviewer set one) > finding's
        # visual_evidence (the original AI-derived shape). Without this
        # the override path strips Phase 2 styling and a reviewed report
        # silently regresses to generic .hotspot rules. Closes Codex
        # review note 3 on commit 3e502e2.
        visual_evidence = (
            marker.get("visual_evidence")
            or (finding.get("visual_evidence") if isinstance(finding.get("visual_evidence"), dict) else None)
        )
        out = {
            "number": finding.get("cluster_index") or finding.get("index"),
            "finding_index": finding.get("index"),
            "f_ref": ref,
            "x_pct": max(0.0, min(100.0, x + w / 2 if w else x)),
            "y_pct": max(0.0, min(100.0, y + h / 2 if h else y)),
            "severity": (marker.get("severity") or finding.get("priority") or "medium").lower(),
            "fallback_role": None,
            "match_method": "review_state",
            "shape": shape,
            "stroke": marker.get("stroke"),
            "highlight_style": marker.get("highlight_style"),
            "spotlight_visible": marker.get("spotlight_visible"),
            "fill_opacity": marker.get("fill_opacity"),
            "glow_opacity": marker.get("glow_opacity"),
            "visual_evidence": visual_evidence,
        }
        if w >= 1 and h >= 1:
            out["zone"] = {
                "left_pct": max(0.0, min(100.0, x)),
                "top_pct": max(0.0, min(100.0, y)),
                "w_pct": max(0.0, min(100.0 - max(0.0, min(100.0, x)), w)),
                "h_pct": max(0.0, min(100.0 - max(0.0, min(100.0, y)), h)),
            }
        patched.setdefault(slide_idx, []).append(out)

    return patched
