"""Review-state builder and renderer for the ECP human editor.

The review state is the operator-owned presentation layer. It is generated
from v2 audit artifacts, then edited by a human without mutating baton files,
cluster emissions, synthesizer output, or the AI draft visual reports.
"""
from __future__ import annotations

import base64
import html
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CURRENT_REVIEW_STATE_VERSION = 1
REVIEW_STATE_FILENAMES = {
    "desktop": "review-state-desktop.json",
    "mobile": "review-state-mobile.json",
    "laptop": "review-state-laptop.json",
}


def build_initial_review_state(
    engagement_dir: Path,
    device: str,
    *,
    plugin_root: Path | None = None,
    audit_file: str | None = None,
    baton_file: str | None = None,
) -> dict[str, Any]:
    """Build a v1 review-state dict from an existing v2 engagement."""
    from report import html_builder as v1
    from report.geometry import backfill_screenshots_from_sections
    from report.v2_loader import load_v2_engagement
    from report.v2_markers import auto_map_markers_v2, compute_marker_positions_v2
    from report.templates.components import assign_cluster_indices

    engagement_dir = Path(engagement_dir)
    if plugin_root is None:
        parents = list(engagement_dir.resolve().parents)
        plugin_root = parents[2] if len(parents) >= 3 else engagement_dir
    plugin_root = Path(plugin_root)
    audit_file = audit_file or f"audit-{device}.md"
    baton_file = baton_file or ("baton.json" if device in ("desktop", "laptop") else f"baton-{device}.json")

    inputs = load_v2_engagement(
        engagement_dir,
        device,
        plugin_root,
        audit_file=audit_file,
        baton_file=baton_file,
    )
    baton = inputs["baton"]
    backfill_screenshots_from_sections(baton, engagement_dir)
    assign_cluster_indices(inputs["findings"])

    auto_mapped = auto_map_markers_v2(inputs["findings"], baton)
    slide_markers = compute_marker_positions_v2(auto_mapped, baton)
    marker_by_ref = _markers_by_ref(slide_markers)
    mapping_by_ref = {m.get("f_ref"): m for m in auto_mapped if m.get("f_ref")}

    now = _utc_now()
    engagement_id = _engagement_id(engagement_dir, inputs.get("meta"))
    slides = _build_slides(baton, device)
    markers: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    for finding in inputs["findings"]:
        f_ref = finding.get("f_ref") or f"{finding.get('cluster', 'finding')}/F-{finding.get('index', 0):02d}"
        slug = _slug(f_ref)
        ai_marker = marker_by_ref.get(f_ref)
        mapping = mapping_by_ref.get(f_ref, {})
        marker_id = f"marker-{slug}"
        ai_marker_id = f"{marker_id}-ai"
        slide_id = _slide_id(device, ai_marker.get("slide", 0) if ai_marker else mapping.get("slide", 0))
        severity = finding.get("severity") or finding.get("priority") or ""

        # Strategy 4 "unplaced" findings carry no position (product.md §4.2):
        # build a blank, hidden marker so the renderer leaves it empty and the
        # editor queues it for manual placement, instead of pinning a default
        # point at the slide center.
        if mapping.get("match_method") == "unplaced":
            marker = _unplaced_marker(
                marker_id, f_ref, slide_id, severity, mapping.get("visual_evidence")
            )
        else:
            marker = _marker_from_ai(marker_id, f_ref, slide_id, ai_marker, mapping, severity)
        ai_copy = dict(marker)
        ai_copy["marker_id"] = ai_marker_id
        ai_copy["source"] = _marker_source(mapping.get("match_method"))
        markers.extend([marker, ai_copy])

        summary = finding.get("plain_english_summary") or finding.get("observation") or finding.get("title", "")
        action = finding.get("plain_english_action") or finding.get("recommendation") or ""
        findings.append({
            "f_ref": f_ref,
            "status": "needs_review",
            "cluster": finding.get("cluster", ""),
            "severity": finding.get("severity") or finding.get("priority", ""),
            # Phase 3 hardening (2026-05-18) — preserve ethics_state and
            # verdict so check_priority_path_needs_review can identify
            # ADJACENT/BLOCK ethics findings in review-state output.
            # Without these fields the gate only catches findings that
            # are ALSO in Priority Path; a standalone ADJACENT ethics
            # shipping with needs_review confidence slips through.
            # Closes Codex review note 4 on commit 3e502e2.
            "ethics_state": finding.get("ethics_state") or "",
            "verdict": finding.get("verdict") or finding.get("priority") or "",
            "finding_title": finding.get("title", ""),
            "finding_title_override": None,
            "finding_body": summary,
            "finding_body_override": None,
            "observation": finding.get("observation", ""),
            "observation_override": None,
            "recommendation": finding.get("recommendation", ""),
            "recommendation_override": None,
            "why_this_matters": finding.get("why_matters", ""),
            "why_this_matters_override": None,
            "callout_title": finding.get("title", ""),
            "callout_title_override": None,
            "callout_body": action,
            "callout_color": severity_stroke(severity),
            "callout_slide_id": slide_id,
            "callout_position": _default_callout_position(marker),
            "callout_visible": True,
            "marker_id": marker_id,
            "ai_suggested_marker_id": ai_marker_id,
            "lint_violations": [],
            "hotspot_confidence": _hotspot_confidence(mapping.get("match_method")),
            "visual_evidence": mapping.get("visual_evidence"),
            "review_notes": "",
            "tagged_for_ai_pass": False,
            "ai_pass_instruction": None,
            "reviewed_at": None,
            "reviewed_by": None,
            "raw": {
                "index": finding.get("index"),
                "baton_index": finding.get("baton_index"),
                "match_method": mapping.get("match_method"),
                "element": finding.get("element", ""),
                "section": finding.get("section", ""),
            },
        })

    state = {
        "review_state_schema_version": CURRENT_REVIEW_STATE_VERSION,
        "engagement_id": engagement_id,
        "ai_draft_artifact": _draft_artifact(device),
        "created_at": now,
        "updated_at": now,
        "device": device,
        "findings": findings,
        "markers": markers,
        "slides": slides,
        "slide_edits": [_default_slide_edit(slide["slide_id"]) for slide in slides],
        "imported_assets": [],
        "audit_metadata": _audit_metadata(inputs, engagement_id),
    }
    errors = validate_review_state(state)
    if errors:
        raise ValueError("review-state validation failed: " + "; ".join(errors[:5]))
    return state


def validate_review_state(review_state: dict[str, Any]) -> list[str]:
    """Validate review state against schema, with a lightweight fallback."""
    schema_path = Path(__file__).resolve().parents[2] / "schema" / "review-state-v1.json"
    schema_errors: list[str] = []
    try:
        from jsonschema import Draft202012Validator

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        schema_errors = [
            f"{'.'.join(str(p) for p in error.absolute_path) or '(root)'}: {error.message}"
            for error in sorted(validator.iter_errors(review_state), key=lambda e: list(e.absolute_path))
        ]
    except Exception:
        schema_errors = _validate_review_state_lightweight(review_state)

    return schema_errors + _validate_review_state_references(review_state)


def _validate_review_state_lightweight(review_state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if review_state.get("review_state_schema_version") != CURRENT_REVIEW_STATE_VERSION:
        errors.append("review_state_schema_version must be 1")
    for key in ("engagement_id", "device", "findings", "markers", "slides", "slide_edits"):
        if key not in review_state:
            errors.append(f"missing required key: {key}")
    if not isinstance(review_state.get("findings"), list):
        errors.append("findings must be an array")
    if not isinstance(review_state.get("markers"), list):
        errors.append("markers must be an array")
    for i, finding in enumerate(review_state.get("findings", [])):
        if finding.get("status") not in {"needs_review", "approved", "edited", "hidden", "tagged_for_ai_pass"}:
            errors.append(f"findings[{i}].status is invalid")
    return errors


def _validate_review_state_references(review_state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    marker_ids = {m.get("marker_id") for m in review_state.get("markers", []) if isinstance(m, dict)}
    slide_ids = {s.get("slide_id") for s in review_state.get("slides", []) if isinstance(s, dict)}
    for i, finding in enumerate(review_state.get("findings", [])):
        if finding.get("marker_id") not in marker_ids:
            errors.append(f"findings[{i}].marker_id does not reference markers[]")
        callout_slide_id = finding.get("callout_slide_id")
        if callout_slide_id and callout_slide_id not in slide_ids:
            errors.append(f"findings[{i}].callout_slide_id does not reference slides[]")
    for i, marker in enumerate(review_state.get("markers", [])):
        if marker.get("shape") not in {"point", "rect", "ellipse", "polygon", "freeform", "snap-to-element"}:
            errors.append(f"markers[{i}].shape is invalid")
        if marker.get("slide_id") not in slide_ids:
            errors.append(f"markers[{i}].slide_id does not reference slides[]")
    return errors


def migrate_review_state(review_state: dict[str, Any]) -> dict[str, Any]:
    """Migrate a review state to the current schema version."""
    version = review_state.get("review_state_schema_version")
    if version == CURRENT_REVIEW_STATE_VERSION:
        return review_state
    if version is None:
        raise ValueError("review state is missing review_state_schema_version")
    if version > CURRENT_REVIEW_STATE_VERSION:
        raise ValueError("review state was produced by a newer editor")
    raise ValueError(f"no migration available from review-state v{version}")


def write_review_state(
    engagement_dir: Path,
    device: str,
    *,
    plugin_root: Path | None = None,
    output_file: str | None = None,
    overwrite: bool = False,
) -> Path:
    """Build and write review-state-{device}.json."""
    out = Path(engagement_dir) / (output_file or REVIEW_STATE_FILENAMES.get(device, f"review-state-{device}.json"))
    if out.exists() and not overwrite:
        return out
    if out.exists() and overwrite:
        backup = out.with_name(f"{out.stem}.backup{out.suffix}")
        shutil.copy2(out, backup)
    state = build_initial_review_state(engagement_dir, device, plugin_root=plugin_root)
    out.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def generate_editor_artifacts(
    engagement_dir: Path,
    plugin_root: Path,
    *,
    devices: list[str] | None = None,
    overwrite_review_state: bool = False,
) -> dict[str, Path]:
    """Write review states for available devices and a self-contained editor.html."""
    engagement_dir = Path(engagement_dir)
    plugin_root = Path(plugin_root)
    devices = devices or _available_devices(engagement_dir)
    states: dict[str, dict[str, Any]] = {}
    snap_targets: dict[str, dict[str, list[dict[str, Any]]]] = {}
    outputs: dict[str, Path] = {}
    for device in devices:
        state_path = write_review_state(
            engagement_dir,
            device,
            plugin_root=plugin_root,
            overwrite=overwrite_review_state,
        )
        outputs[f"review_state_{device}"] = state_path
        states[device] = json.loads(state_path.read_text(encoding="utf-8"))
        snap_targets[device] = _build_snap_targets(engagement_dir, plugin_root, device)
    if states:
        editor_html = render_editor_html(engagement_dir, plugin_root, states, snap_targets=snap_targets)
        editor_path = engagement_dir / "editor.html"
        editor_path.write_text(editor_html, encoding="utf-8")
        outputs["editor"] = editor_path
    return outputs


def _build_snap_targets(engagement_dir: Path, plugin_root: Path, device: str) -> dict[str, list[dict[str, Any]]]:
    """Per-slide snap targets from baton element bboxes (in slide-relative %)."""
    from report.geometry import (
        backfill_screenshots_from_sections,
        element_rect_css,
        infer_element_coord_scale,
        viewport_dpr,
    )
    from report.v2_loader import load_v2_engagement

    audit_file = f"audit-{device}.md"
    baton_file = "baton.json" if device in ("desktop", "laptop") else f"baton-{device}.json"
    try:
        inputs = load_v2_engagement(engagement_dir, device, plugin_root, audit_file=audit_file, baton_file=baton_file)
    except Exception:
        return {}
    baton = inputs.get("baton") or {}
    viewport = baton.get("viewport") or {}
    backfill_screenshots_from_sections(baton, engagement_dir)
    screenshots = baton.get("screenshots") or []
    page_w = float(viewport.get("width") or 1920)
    sections = baton.get("sections") or []
    elements = baton.get("elements") or []
    scale = infer_element_coord_scale(
        elements,
        screenshots,
        viewport,
        viewport_dpr(viewport),
        sections,
    )
    out: dict[str, list[dict[str, Any]]] = {}
    for i, section in enumerate(sections):
        slide_id = _slide_id(device, i)
        top = float(section.get("scroll_y_top") or 0)
        bot = float(section.get("scroll_y_bottom") or top + 1080)
        section_h = max(bot - top, 1.0)
        targets: list[dict[str, Any]] = []
        for el in elements:
            rect = element_rect_css(el, scale) or {}
            ex = float(rect.get("x") or 0)
            ey = float(rect.get("y") or 0)
            ew = float(rect.get("width") or 0)
            eh = float(rect.get("height") or 0)
            if ew <= 1 or eh <= 1:
                continue
            center_y = ey + eh / 2
            if center_y < top or center_y >= bot:
                continue
            x_pct = max(0.0, min(100.0, (ex / page_w) * 100))
            w_pct = max(0.5, min(100.0 - x_pct, (ew / page_w) * 100))
            y_pct = max(0.0, min(100.0, ((ey - top) / section_h) * 100))
            h_pct = max(0.5, min(100.0 - y_pct, (eh / section_h) * 100))
            targets.append({
                "e_index": el.get("e_index"),
                "label": (el.get("text_content") or el.get("role") or el.get("tag") or "")[:60],
                "x_pct": round(x_pct, 2),
                "y_pct": round(y_pct, 2),
                "w_pct": round(w_pct, 2),
                "h_pct": round(h_pct, 2),
            })
        out[slide_id] = targets
    return out


def render_final_report(review_state: dict[str, Any], engagement_dir: Path, device: str | None = None) -> str:
    """Render a self-contained read-only HTML report from review-state."""
    review_state = migrate_review_state(review_state)
    errors = validate_review_state(review_state)
    if errors:
        raise ValueError("review-state failed validation: " + "; ".join(errors[:5]))
    device = device or review_state.get("device", "desktop")
    engagement_dir = Path(engagement_dir)
    images = _slide_images(review_state, engagement_dir)
    meta = review_state.get("audit_metadata") or {}
    title = f"ECP Final Visual Report - {html.escape(str(meta.get('url') or review_state.get('engagement_id')))}"
    visible_findings = [f for f in review_state.get("findings", []) if f.get("status") != "hidden"]
    markers_by_id = {m.get("marker_id"): m for m in review_state.get("markers", [])}
    findings_by_slide: dict[str, list[dict[str, Any]]] = {}
    callouts_by_slide: dict[str, list[dict[str, Any]]] = {}
    for finding in visible_findings:
        marker = markers_by_id.get(finding.get("marker_id"))
        if marker:
            marker_slide_id = marker.get("slide_id")
            findings_by_slide.setdefault(marker_slide_id, []).append(finding)
            callout_slide_id = finding.get("callout_slide_id") or marker_slide_id
            callouts_by_slide.setdefault(callout_slide_id, []).append(finding)

    slide_html = []
    for slide in review_state.get("slides", []):
        sid = slide.get("slide_id")
        img = images.get(sid, "")
        slide_findings = findings_by_slide.get(sid, [])
        slide_markers = [markers_by_id.get(f.get("marker_id")) for f in slide_findings]
        slide_callouts = callouts_by_slide.get(sid, [])
        callout_markers = [markers_by_id.get(f.get("marker_id")) for f in slide_callouts]
        overlays = "".join(_render_marker_svg(m, f) for m, f in zip(slide_markers, slide_findings))
        connectors = "".join(
            _render_connector(m, f)
            for m, f in zip(callout_markers, slide_callouts)
            if m and m.get("slide_id") == sid
        )
        callouts = "".join(_render_callout(m, f) for m, f in zip(callout_markers, slide_callouts))
        effects = _render_effects(review_state, sid)
        edit = _slide_edit(review_state, sid)
        img_style = _image_edit_style(edit)
        spotlight = _render_spotlight(sid, slide_markers, slide_findings, edit)
        slide_refs = {str(f.get("f_ref")) for f in [*slide_findings, *slide_callouts] if f.get("f_ref")}
        slide_html.append(
            f'<section class="slide-card" id="{html.escape(str(sid))}">'
            f'<div class="slide-heading"><span>{html.escape(str(slide.get("section_label") or sid))}</span>'
            f'<small>{len(slide_refs)} findings</small></div>'
            '<div class="slide-stage">'
            f'<div class="slide-canvas" style="{img_style}">'
            f'<img src="{img}" alt="{html.escape(str(slide.get("section_label") or sid))}">'
            f'<svg class="marker-layer" viewBox="0 0 100 100" preserveAspectRatio="none">{spotlight}{connectors}{overlays}</svg>'
            f'{effects}{callouts}'
            '</div></div></section>'
        )

    finding_rows = "".join(
        f'<li>'
        f'<span class="sev-dot" style="background:{severity_stroke(f.get("severity"))}" title="{html.escape(str(f.get("severity") or ""))}"></span>'
        f'<div class="row-body"><strong>{html.escape(_display_title(f))}</strong>'
        f'<span class="row-meta">{html.escape(str(f.get("cluster") or ""))} · {html.escape(str(f.get("status") or ""))}</span>'
        f'</div></li>'
        for f in visible_findings
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>{_final_report_css()}</style>
</head>
<body>
  <header class="hero">
    <p class="eyebrow">Human-reviewed ECP audit</p>
    <h1>{title}</h1>
    <p>{html.escape(str(meta.get("page_type") or ""))} audit · {html.escape(str(device))} · {len(visible_findings)} visible findings</p>
  </header>
  <main>
    <aside class="summary"><h2>Findings</h2><ol>{finding_rows}</ol></aside>
    <div class="slides">{''.join(slide_html)}</div>
  </main>
</body>
</html>
"""


def render_editor_html(engagement_dir: Path, plugin_root: Path, states: dict[str, dict[str, Any]], snap_targets: dict[str, dict[str, list[dict[str, Any]]]] | None = None) -> str:
    """Render tools/editor/index.html with inline state, screenshots, CSS, and JS."""
    editor_dir = Path(plugin_root) / "tools" / "editor"
    template = (editor_dir / "index.html").read_text(encoding="utf-8")
    css = (editor_dir / "editor.css").read_text(encoding="utf-8")
    js = (editor_dir / "editor.js").read_text(encoding="utf-8")
    image_payload = {
        device: _slide_images(state, engagement_dir)
        for device, state in states.items()
    }
    payload = {
        "schema_version": CURRENT_REVIEW_STATE_VERSION,
        "devices": list(states.keys()),
        "states": states,
        "slide_images": image_payload,
        "snap_targets": snap_targets or {},
    }
    return (
        template
        .replace("/*__EDITOR_CSS__*/", css)
        .replace("//__EDITOR_JS__", js)
        .replace(
            "__REVIEW_STATE_JSON__",
            json.dumps(payload, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--"),
        )
    )


def _ensure_v1_screenshots(baton: dict[str, Any], engagement_dir: Path | None = None) -> None:
    from report.geometry import backfill_screenshots_from_sections

    backfill_screenshots_from_sections(baton, engagement_dir)


def _available_devices(engagement_dir: Path) -> list[str]:
    devices: list[str] = []
    if (engagement_dir / "baton.json").exists() and (engagement_dir / "audit-desktop.md").exists():
        devices.append("desktop")
    if (engagement_dir / "baton-mobile.json").exists() and (engagement_dir / "audit-mobile.md").exists():
        devices.append("mobile")
    if not devices and (engagement_dir / "baton.json").exists():
        devices.append("desktop")
    return devices


def _build_slides(baton: dict[str, Any], device: str) -> list[dict[str, Any]]:
    screenshots = baton.get("screenshots") or []
    sections = baton.get("sections") or []
    slides = []
    for i, screenshot in enumerate(screenshots):
        section = sections[i] if i < len(sections) else {}
        source = screenshot.get("path") or screenshot.get("file") or section.get("screenshot_ref") or f"section-{i + 1}.jpg"
        slides.append({
            "slide_id": _slide_id(device, i),
            "source": source,
            "viewport": device,
            "device": device,
            "section_index": i,
            "section_label": screenshot.get("label") or section.get("label") or section.get("slug") or f"Section {i + 1}",
            "scroll_y_top": section.get("scroll_y_top", screenshot.get("scrollY", 0)),
            "scroll_y_bottom": section.get("scroll_y_bottom"),
            "natural_width": screenshot.get("naturalWidth") or screenshot.get("width") or (baton.get("viewport") or {}).get("width"),
            "natural_height": screenshot.get("naturalHeight") or screenshot.get("height") or (baton.get("viewport") or {}).get("height"),
            "user_imported": False,
        })
    return slides


def _markers_by_ref(slide_markers: dict[Any, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    out = {}
    for slide, markers in slide_markers.items():
        for marker in markers:
            if marker.get("f_ref"):
                copy = dict(marker)
                copy["slide"] = int(slide)
                out[marker["f_ref"]] = copy
    return out


SEVERITY_STROKES = {
    "critical": "#EF4444",
    "high": "#F97316",
    "medium": "#FACC15",
    "low": "#60A5FA",
    "info": "#9CA3AF",
}


def severity_stroke(severity: str | None) -> str:
    """Map a finding severity (or priority) to a marker stroke color."""
    return SEVERITY_STROKES.get((severity or "").strip().lower(), "#FACC15")


def _marker_from_ai(
    marker_id: str,
    f_ref: str,
    slide_id: str,
    ai_marker: dict[str, Any] | None,
    mapping: dict[str, Any],
    severity: str | None = None,
) -> dict[str, Any]:
    ai_marker = ai_marker or {}
    zone = ai_marker.get("zone") or {}
    stroke = severity_stroke(severity)
    # Phase 3 hardening (2026-05-18) — surface visual_evidence on the
    # marker itself, not just the parallel findings array. The Phase 3
    # giant-rectangle gate reads markers; without this field the gate
    # silently skips every marker as "legacy" (false pass). See Codex
    # review note 1 + 2 on the 3e502e2 commit.
    visual_evidence = mapping.get("visual_evidence")
    if zone:
        return {
            "marker_id": marker_id,
            "f_ref": f_ref,
            "slide_id": slide_id,
            "shape": "rect",
            "x_pct": round(float(zone.get("left_pct", 0)), 3),
            "y_pct": round(float(zone.get("top_pct", 0)), 3),
            "w_pct": round(float(zone.get("w_pct", 6)), 3),
            "h_pct": round(float(zone.get("h_pct", 4)), 3),
            "stroke": stroke,
            "stroke_width": 3,
            "source": _marker_source(mapping.get("match_method")),
            "snapped_baton_index": mapping.get("baton_element_index"),
            "severity": severity or "",
            "visual_evidence": visual_evidence,
        }
    return {
        "marker_id": marker_id,
        "f_ref": f_ref,
        "slide_id": slide_id,
        "shape": "point",
        "cx_pct": round(float(ai_marker.get("x_pct", 50)), 3),
        "cy_pct": round(float(ai_marker.get("y_pct", 50)), 3),
        "stroke": stroke,
        "stroke_width": 3,
        "source": _marker_source(mapping.get("match_method")),
        "snapped_baton_index": mapping.get("baton_element_index"),
        "severity": severity or "",
        "visual_evidence": visual_evidence,
    }


def _unplaced_marker(
    marker_id: str,
    f_ref: str,
    slide_id: str,
    severity: str | None,
    visual_evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a blank, hidden marker for an unplaced finding (product.md §4.2).

    Strategy 4 in v2_markers leaves the hotspot blank rather than auto-placing
    a guess. The marker carries NO coordinates and ``hidden=True`` so the
    renderer draws nothing (``_render_marker_svg`` short-circuits on hidden)
    and the editor's ``isMarkerPlaced`` returns false — surfacing the finding
    in the "Place manually" queue. Mirrors the editor's own
    ``clearActiveMarkerPlacement`` representation so a freshly-generated blank
    is indistinguishable from one the operator cleared by hand.
    """
    return {
        "marker_id": marker_id,
        "f_ref": f_ref,
        "slide_id": slide_id,
        "shape": "point",
        "hidden": True,
        "stroke": severity_stroke(severity),
        "stroke_width": 3,
        "source": "manual",
        "snapped_baton_index": None,
        "severity": severity or "",
        "visual_evidence": visual_evidence,
    }


def _default_callout_position(marker: dict[str, Any]) -> dict[str, float | str]:
    x = marker.get("cx_pct", marker.get("x_pct", 50))
    y = marker.get("cy_pct", marker.get("y_pct", 50))
    return {
        "x_pct": min(74, max(4, float(x) + 8)),
        "y_pct": min(82, max(4, float(y) - 8)),
        "w_pct": 22,
        "h_pct": 8,
        "anchor": "auto",
    }


def _default_slide_edit(slide_id: str) -> dict[str, Any]:
    return {
        "slide_id": slide_id,
        "crop": {"x_pct": 0, "y_pct": 0, "w_pct": 100, "h_pct": 100},
        "transform": {"scale": 1.0, "rotate_deg": 0, "translate_x_pct": 0, "translate_y_pct": 0},
        "effects": [],
    }


def _slide_images(review_state: dict[str, Any], engagement_dir: Path) -> dict[str, str]:
    images = {}
    imported = {
        asset.get("asset_id"): asset
        for asset in review_state.get("imported_assets", [])
        if isinstance(asset, dict)
    }
    for slide in review_state.get("slides", []):
        sid = slide.get("slide_id")
        if not sid:
            continue
        asset = imported.get(slide.get("asset_id"))
        if asset and asset.get("source"):
            asset_path = engagement_dir / str(asset.get("source"))
            images[sid] = _image_data_url(asset_path, engagement_dir) or asset.get("data_url", "")
            continue
        if asset and asset.get("data_url"):
            images[sid] = asset["data_url"]
            continue
        path = engagement_dir / str(slide.get("source", ""))
        images[sid] = _image_data_url(path, engagement_dir) if path.exists() else ""
    return images


def _image_data_url(path: Path, engagement_dir: Path) -> str:
    try:
        resolved = path.resolve()
        base = engagement_dir.resolve()
        if not resolved.is_relative_to(base):
            return ""
        raw = resolved.read_bytes()
    except OSError:
        return ""
    mime = "image/png" if raw.startswith(b"\x89PNG") else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def _render_marker_svg(marker: dict[str, Any] | None, finding: dict[str, Any]) -> str:
    if not marker or marker.get("hidden") is True:
        return ""
    label = html.escape(str(finding.get("f_ref", "")))
    stroke = html.escape(str(marker.get("stroke") or "#FACC15"))
    style = _dominant_marker_style(marker)
    sw = _marker_stroke_width(marker) / 10
    fill_opacity = _marker_fill_opacity(marker)
    fill = stroke if fill_opacity > 0 else "transparent"
    shape_stroke = stroke if _marker_style_enabled(marker, "outline") else "transparent"
    style_attr = ""
    if _marker_glow_opacity(marker) > 0:
        style_attr = f' style="filter:drop-shadow(0 0 2px {stroke})"'
    glow = _marker_glow_svg(marker, stroke, sw)
    shape = marker.get("shape")
    if shape == "rect":
        rect = (
            f'<rect x="{marker.get("x_pct", 0)}" y="{marker.get("y_pct", 0)}" '
            f'width="{marker.get("w_pct", 6)}" height="{marker.get("h_pct", 4)}" '
            f'fill="{fill}" fill-opacity="{fill_opacity}" stroke="{shape_stroke}" stroke-width="{sw}" '
            f'rx="1" ry="1"{style_attr}><title>{label}</title></rect>'
        )
        if _marker_style_enabled(marker, "underline"):
            x = float(marker.get("x_pct", 0) or 0)
            y = float(marker.get("y_pct", 0) or 0) + float(marker.get("h_pct", 4) or 4)
            w = float(marker.get("w_pct", 6) or 6)
            underline = (
                f'<line x1="{x}" y1="{y}" x2="{x + w}" y2="{y}" stroke="{stroke}" '
                f'stroke-width="{max(sw * 1.8, 0.6)}" vector-effect="non-scaling-stroke"></line>'
            )
            return glow + rect + underline
        return glow + rect
    if shape == "ellipse":
        return glow + (
            f'<ellipse cx="{marker.get("cx_pct", 50)}" cy="{marker.get("cy_pct", 50)}" '
            f'rx="{marker.get("rx_pct", 5)}" ry="{marker.get("ry_pct", 3)}" '
            f'fill="{fill}" fill-opacity="{fill_opacity}" stroke="{shape_stroke}" stroke-width="{sw}"{style_attr}>'
            f'<title>{label}</title></ellipse>'
        )
    if shape == "polygon":
        pts = _points_attr(marker.get("points"))
        if pts:
            return glow + (
                f'<polygon points="{pts}" fill="{fill}" fill-opacity="{fill_opacity}" '
                f'stroke="{shape_stroke}" stroke-width="{sw}" stroke-linejoin="round"{style_attr}>'
                f'<title>{label}</title></polygon>'
            )
    if shape == "freeform":
        d = _path_d(marker.get("points"), closed=bool(marker.get("closed", True)))
        if d:
            return glow + (
                f'<path d="{d}" fill="{fill}" fill-opacity="{fill_opacity}" '
                f'stroke="{shape_stroke}" stroke-width="{sw}" stroke-linecap="round" '
                f'stroke-linejoin="round"{style_attr}><title>{label}</title></path>'
            )
    return glow + (
        f'<circle cx="{marker.get("cx_pct", 50)}" cy="{marker.get("cy_pct", 50)}" r="1.8" '
        f'fill="{fill if fill != "transparent" else "#111827"}" fill-opacity="{max(fill_opacity, 1 if fill == "transparent" else fill_opacity)}" '
        f'stroke="{shape_stroke}" stroke-width="{sw}"{style_attr}><title>{label}</title></circle>'
    )


def _bounded_float(value: Any, fallback: float, low: float, high: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        out = fallback
    return max(low, min(high, out))


def _marker_fill_opacity(marker: dict[str, Any]) -> float:
    return _bounded_float(marker.get("fill_opacity", 0.0), 0.0, 0.0, 0.8)


def _marker_glow_opacity(marker: dict[str, Any]) -> float:
    fallback = 0.72 if str(marker.get("highlight_style") or "") == "glow" else 0.0
    return _bounded_float(marker.get("glow_opacity", fallback), fallback, 0.0, 1.0)


def _marker_stroke_width(marker: dict[str, Any]) -> float:
    return _bounded_float(marker.get("stroke_width", 3.0), 3.0, 1.0, 12.0)


def _marker_style_enabled(marker: dict[str, Any], key: str) -> bool:
    style = str(marker.get("highlight_style") or "outline")
    if key == "outline":
        return marker.get("outline_visible") is not False
    if key == "fill":
        return _marker_fill_opacity(marker) > 0
    if key == "glow":
        return _marker_glow_opacity(marker) > 0
    if key == "underline":
        return marker.get("underline_visible") is True or style == "underline"
    if key == "spotlight":
        return marker.get("spotlight_visible") is True or style == "spotlight"
    return False


def _dominant_marker_style(marker: dict[str, Any]) -> str:
    for key in ("glow", "fill", "underline", "spotlight", "outline"):
        if _marker_style_enabled(marker, key):
            return key
    return "none"


def _marker_glow_svg(marker: dict[str, Any], stroke: str, sw: float) -> str:
    opacity = _marker_glow_opacity(marker)
    if opacity <= 0:
        return ""
    halo_width = max(sw * 6.5, 1.8)
    style_attr = (
        f'class="marker-glow" style="stroke:{stroke};stroke-width:{halo_width};fill:none;'
        f'opacity:{opacity};--glow-opacity:{opacity};'
        f'filter:drop-shadow(0 0 3px {stroke}) drop-shadow(0 0 14px {stroke}) drop-shadow(0 0 28px {stroke});'
        'pointer-events:none;vector-effect:non-scaling-stroke;"'
    )
    shape = marker.get("shape")
    if shape == "rect":
        return (
            f'<rect {style_attr} x="{marker.get("x_pct", 0)}" y="{marker.get("y_pct", 0)}" '
            f'width="{marker.get("w_pct", 6)}" height="{marker.get("h_pct", 4)}" rx="1" ry="1"></rect>'
        )
    if shape == "ellipse":
        return (
            f'<ellipse {style_attr} cx="{marker.get("cx_pct", 50)}" cy="{marker.get("cy_pct", 50)}" '
            f'rx="{marker.get("rx_pct", 5)}" ry="{marker.get("ry_pct", 3)}"></ellipse>'
        )
    if shape == "polygon":
        pts = _points_attr(marker.get("points"))
        return f'<polygon {style_attr} points="{pts}" stroke-linejoin="round"></polygon>' if pts else ""
    if shape == "freeform":
        d = _path_d(marker.get("points"), closed=bool(marker.get("closed", True)))
        return f'<path {style_attr} d="{d}" stroke-linecap="round" stroke-linejoin="round"></path>' if d else ""
    return f'<circle {style_attr} cx="{marker.get("cx_pct", 50)}" cy="{marker.get("cy_pct", 50)}" r="2.1"></circle>'


def _points_attr(points: Any) -> str:
    if not isinstance(points, list):
        return ""
    parts = []
    for p in points:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            parts.append(f"{float(p[0])},{float(p[1])}")
        elif isinstance(p, dict) and "x" in p and "y" in p:
            parts.append(f"{float(p['x'])},{float(p['y'])}")
    return " ".join(parts)


def _path_d(points: Any, closed: bool = True) -> str:
    pts = _points_attr(points).split()
    if not pts:
        return ""
    head, tail = pts[0], pts[1:]
    parts = [f"M {head}"] + [f"L {p}" for p in tail]
    if closed:
        parts.append("Z")
    return " ".join(parts)


def _render_callout(marker: dict[str, Any] | None, finding: dict[str, Any]) -> str:
    if not marker or not finding.get("callout_visible", True):
        return ""
    pos = finding.get("callout_position") or _default_callout_position(marker)
    title = html.escape(str(finding.get("callout_title_override") or finding.get("callout_title") or _display_title(finding)))
    body = html.escape(str(finding.get("callout_body") or finding.get("recommendation_override") or finding.get("recommendation") or ""))
    stroke = _callout_stroke(finding)
    return (
        f'<article class="callout" style="left:{pos.get("x_pct", 64)}%;top:{pos.get("y_pct", 20)}%;'
        f'width:{pos.get("w_pct", 22)}%;border-color:{stroke};">'
        f'<strong style="color:{stroke}">{title}</strong><p>{body}</p></article>'
    )


def _render_connector(marker: dict[str, Any] | None, finding: dict[str, Any]) -> str:
    if not marker or not finding.get("callout_visible", True):
        return ""
    center = _marker_center(marker)
    pos = finding.get("callout_position") or _default_callout_position(marker)
    callout_w = float(pos.get("w_pct", 22) or 22)
    callout_h = float(pos.get("h_pct", 0) or 0) or 8.0  # h is rarely set; conservative default
    cx = float(pos.get("x_pct", 64)) + callout_w / 2
    cy = float(pos.get("y_pct", 20)) + callout_h / 2
    anchor = pos.get("anchor") or "auto"
    if anchor == "auto":
        anchor = _auto_callout_anchor(center, pos, callout_w, callout_h)
    tip = _callout_edge_point(pos, callout_w, callout_h, anchor)
    stroke = _callout_stroke(finding)
    return (
        f'<line class="connector-line" x1="{center["x"]}" y1="{center["y"]}" '
        f'x2="{tip["x"]}" y2="{tip["y"]}" style="stroke:{stroke}"></line>'
        f'{_render_arrow_head(center, tip, stroke)}'
    )


def _auto_callout_anchor(marker_center: dict[str, float], pos: dict[str, Any], cw: float, ch: float) -> str:
    """Pick the callout edge whose midpoint is closest to the marker center."""
    left = float(pos.get("x_pct", 64))
    top = float(pos.get("y_pct", 20))
    edges = {
        "left": (left, top + ch / 2),
        "right": (left + cw, top + ch / 2),
        "top": (left + cw / 2, top),
        "bottom": (left + cw / 2, top + ch),
    }
    mx, my = marker_center["x"], marker_center["y"]
    return min(edges, key=lambda e: (edges[e][0] - mx) ** 2 + (edges[e][1] - my) ** 2)


def _callout_edge_point(pos: dict[str, Any], cw: float, ch: float, anchor: str) -> dict[str, float]:
    left = float(pos.get("x_pct", 64))
    top = float(pos.get("y_pct", 20))
    if anchor == "left":
        return {"x": left, "y": top + ch / 2}
    if anchor == "right":
        return {"x": left + cw, "y": top + ch / 2}
    if anchor == "bottom":
        return {"x": left + cw / 2, "y": top + ch}
    return {"x": left + cw / 2, "y": top}  # top default


def _render_arrow_head(start: dict[str, float], tip: dict[str, float], stroke: str) -> str:
    """Tiny triangle at the tip, pointing from callout toward marker (i.e. toward `start`)."""
    import math

    dx = start["x"] - tip["x"]
    dy = start["y"] - tip["y"]
    dist = math.hypot(dx, dy)
    if dist < 0.001:
        return ""
    ux, uy = dx / dist, dy / dist
    head_len = 1.6
    head_w = 0.9
    bx, by = tip["x"] + ux * head_len, tip["y"] + uy * head_len
    px, py = -uy, ux
    p1 = f"{tip['x']},{tip['y']}"
    p2 = f"{bx + px * head_w},{by + py * head_w}"
    p3 = f"{bx - px * head_w},{by - py * head_w}"
    return f'<polygon class="connector-arrow" points="{p1} {p2} {p3}" fill="{stroke}"></polygon>'


def _callout_stroke(finding: dict[str, Any]) -> str:
    return html.escape(str(finding.get("callout_color") or severity_stroke(finding.get("severity"))))


def _marker_center(marker: dict[str, Any]) -> dict[str, float]:
    shape = marker.get("shape")
    if shape == "rect":
        return {
            "x": float(marker.get("x_pct", 0)) + float(marker.get("w_pct", 0)) / 2,
            "y": float(marker.get("y_pct", 0)) + float(marker.get("h_pct", 0)) / 2,
        }
    if shape in ("polygon", "freeform"):
        pts = marker.get("points") or []
        if pts:
            xs = [float(p[0]) for p in pts if isinstance(p, (list, tuple)) and len(p) >= 2]
            ys = [float(p[1]) for p in pts if isinstance(p, (list, tuple)) and len(p) >= 2]
            if xs and ys:
                return {"x": sum(xs) / len(xs), "y": sum(ys) / len(ys)}
    return {
        "x": float(marker.get("cx_pct", 50)),
        "y": float(marker.get("cy_pct", 50)),
    }


def _visible_effects(edit: dict[str, Any], f_ref: str | None = None) -> list[dict[str, Any]]:
    effects = [e for e in (edit.get("effects") or []) if not e.get("hidden")]
    if f_ref is None:
        return effects
    return [e for e in effects if e.get("f_ref") == f_ref]


def _render_effects(review_state: dict[str, Any], slide_id: str) -> str:
    edits = _slide_edit(review_state, slide_id)
    html_parts = []
    for effect in _visible_effects(edits):
        if effect.get("type") == "blur":
            r = effect.get("rect") or {}
            feather = max(0.0, min(45.0, float(effect.get("feather_pct", 18) or 18)))
            if effect.get("mode", "outside") == "outside":
                html_parts.append(_render_outside_blur(r, effect))
            else:
                html_parts.append(
                    f'<div class="blur-effect" style="left:{r.get("x_pct", 0)}%;top:{r.get("y_pct", 0)}%;'
                    f'width:{r.get("w_pct", 0)}%;height:{r.get("h_pct", 0)}%;--blur:{effect.get("radius_px", 8)}px;--feather:{feather}%;"></div>'
                )
        if effect.get("type") == "dim" and effect.get("rect"):
            r = effect.get("rect") or {}
            opacity = max(0.0, min(0.95, float(effect.get("opacity", 0.38) or 0.38)))
            html_parts.append(
                f'<div class="dim-region-effect" style="left:{r.get("x_pct", 0)}%;top:{r.get("y_pct", 0)}%;'
                f'width:{r.get("w_pct", 0)}%;height:{r.get("h_pct", 0)}%;--dim-opacity:{opacity};"></div>'
            )
    return "".join(html_parts)


def _render_outside_blur(rect: dict[str, Any], effect: dict[str, Any]) -> str:
    x = _bounded_float(rect.get("x_pct", 0), 0, 0, 99.5)
    y = _bounded_float(rect.get("y_pct", 0), 0, 0, 99.5)
    w = _bounded_float(rect.get("w_pct", 0), 0.5, 0.5, 100 - x)
    h = _bounded_float(rect.get("h_pct", 0), 0.5, 0.5, 100 - y)
    blur = _bounded_float(effect.get("radius_px", 8), 8, 0, 40)
    pieces = [
        (0, 0, 100, y),
        (0, y + h, 100, max(0, 100 - (y + h))),
        (0, y, x, h),
        (x + w, y, max(0, 100 - (x + w)), h),
    ]
    html_parts = []
    for left, top, width, height in pieces:
        if width <= 0 or height <= 0:
            continue
        html_parts.append(
            f'<div class="blur-outside-effect" style="left:{left}%;top:{top}%;'
            f'width:{width}%;height:{height}%;--blur:{blur}px;"></div>'
        )
    html_parts.append(
        f'<div class="blur-focus-effect" style="left:{x}%;top:{y}%;width:{w}%;height:{h}%;"></div>'
    )
    return "".join(html_parts)


def _render_spotlight(
    slide_id: str,
    slide_markers: list[dict[str, Any] | None],
    slide_findings: list[dict[str, Any]],
    edit: dict[str, Any],
) -> str:
    """Render one dim overlay, cutting out only the findings that own dim effects."""
    dims = [e for e in _visible_effects(edit) if e.get("type") == "dim" and not e.get("rect")]
    if not dims:
        return ""
    opacity = max(max(0.0, min(0.95, float(dim.get("opacity", 0.5) or 0.5))) for dim in dims)
    scoped_refs = {str(dim.get("f_ref")) for dim in dims if dim.get("f_ref")}
    if scoped_refs:
        cutout_markers = [
            marker
            for marker, finding in zip(slide_markers, slide_findings)
            if marker and marker.get("hidden") is not True and str(finding.get("f_ref")) in scoped_refs
        ]
    else:
        cutout_markers = [marker for marker in slide_markers if marker and marker.get("hidden") is not True]
    cutouts = "".join(_marker_mask_shape(m) for m in cutout_markers if m)
    mask_id = f"dim-mask-{_slug(str(slide_id))}"
    return (
        f'<defs><mask id="{html.escape(mask_id)}" maskUnits="userSpaceOnUse" '
        f'x="0" y="0" width="100" height="100">'
        f'<rect x="0" y="0" width="100" height="100" fill="white"/>'
        f'{cutouts}'
        f'</mask></defs>'
        f'<rect class="spotlight-dim" x="0" y="0" width="100" height="100" '
        f'fill="black" fill-opacity="{opacity}" mask="url(#{html.escape(mask_id)})"/>'
    )


def _marker_mask_shape(marker: dict[str, Any]) -> str:
    """Black shape on the dim mask = cutout = unmasked = visible (the spotlight hole)."""
    shape = marker.get("shape")
    if shape == "rect":
        return (
            f'<rect x="{marker.get("x_pct", 0)}" y="{marker.get("y_pct", 0)}" '
            f'width="{marker.get("w_pct", 6)}" height="{marker.get("h_pct", 4)}" '
            f'rx="1" ry="1" fill="black"/>'
        )
    if shape == "ellipse":
        return (
            f'<ellipse cx="{marker.get("cx_pct", 50)}" cy="{marker.get("cy_pct", 50)}" '
            f'rx="{marker.get("rx_pct", 5)}" ry="{marker.get("ry_pct", 3)}" fill="black"/>'
        )
    if shape == "polygon":
        pts = _points_attr(marker.get("points"))
        if pts:
            return f'<polygon points="{pts}" fill="black"/>'
    if shape == "freeform":
        d = _path_d(marker.get("points"), closed=True)
        if d:
            return f'<path d="{d}" fill="black"/>'
    return (
        f'<circle cx="{marker.get("cx_pct", 50)}" cy="{marker.get("cy_pct", 50)}" '
        f'r="2.4" fill="black"/>'
    )


def _slide_edit(review_state: dict[str, Any], slide_id: str) -> dict[str, Any]:
    return next((e for e in review_state.get("slide_edits", []) if e.get("slide_id") == slide_id), {})


def _image_edit_style(edit: dict[str, Any]) -> str:
    crop = edit.get("crop") or {}
    transform = edit.get("transform") or {}
    styles: list[str] = []
    if crop and not (
        float(crop.get("x_pct", 0) or 0) == 0
        and float(crop.get("y_pct", 0) or 0) == 0
        and float(crop.get("w_pct", 100) or 100) == 100
        and float(crop.get("h_pct", 100) or 100) == 100
    ):
        right = 100 - (float(crop.get("x_pct", 0) or 0) + float(crop.get("w_pct", 100) or 100))
        bottom = 100 - (float(crop.get("y_pct", 0) or 0) + float(crop.get("h_pct", 100) or 100))
        styles.append(
            f'clip-path:inset({crop.get("y_pct", 0)}% {right}% {bottom}% {crop.get("x_pct", 0)}%)'
        )
    scale = float(transform.get("scale", 1) or 1)
    rotate = float(transform.get("rotate_deg", 0) or 0)
    tx = float(transform.get("translate_x_pct", 0) or 0)
    ty = float(transform.get("translate_y_pct", 0) or 0)
    if scale != 1 or rotate != 0 or tx != 0 or ty != 0:
        styles.append(f"transform:translate({tx}%, {ty}%) rotate({rotate}deg) scale({scale})")
        styles.append("transform-origin:center")
    return ";".join(styles)


def _display_title(finding: dict[str, Any]) -> str:
    return finding.get("finding_title_override") or finding.get("finding_title") or finding.get("callout_title") or finding.get("f_ref", "")


def _hotspot_confidence(match_method: str | None) -> str:
    # Bug B fix (2026-05-02): expand the taxonomy to honestly reflect
    # placement quality. The old map collapsed every Strategy-1 lookup
    # to "exact-selector" even when the element had no geometry or
    # landed off-slide — making the editor's "needs review" filter
    # useless. Off-slide e_index hits now downgrade to "fallback-absence"
    # so they surface in the editor for manual placement. Viewport
    # proposed_anchor is a real positioning signal (page-global sticky
    # CTAs etc), not a manual-placement bail-out — re-label as
    # "section-match". operator_override is a real hand-placed marker
    # and should carry exact-selector confidence.
    # "unplaced" (2026-05-26, G4): Strategy 4 no longer auto-places a banner;
    # it leaves the hotspot blank (product.md §4.2). Map it to needs-manual-
    # marker so the editor surfaces it in the "Place manually" queue. "banner"
    # is retained for back-compat with operator overrides / persisted review
    # states written before the rename.
    return {
        "e_index_lookup": "exact-selector",
        "e_index_lookup_offslide": "fallback-absence",
        "proposed_anchor_element": "exact-selector",
        "proposed_anchor_section": "section-match",
        "proposed_anchor_viewport": "section-match",
        "section_centroid": "section-match",
        "unplaced": "needs-manual-marker",
        "banner": "needs-manual-marker",
        "operator_override": "exact-selector",
    }.get(match_method or "", "needs-manual-marker")


def _marker_source(match_method: str | None) -> str:
    # "unplaced" findings have no placement source — the operator owns it, so
    # it maps to the schema's "manual" source (the default). "banner" is kept
    # for back-compat with persisted states.
    return {
        "e_index_lookup": "e_index_lookup",
        "proposed_anchor_element": "proposed_anchor_element",
        "proposed_anchor_section": "proposed_anchor_section",
        "proposed_anchor_viewport": "proposed_anchor_viewport",
        "section_centroid": "proposed_anchor_section",
        "banner": "proposed_anchor_viewport",
    }.get(match_method or "", "manual")


def _audit_metadata(inputs: dict[str, Any], engagement_id: str) -> dict[str, Any]:
    meta = inputs.get("meta") or {}
    page = meta.get("page") or {}
    return {
        "engagement_id": engagement_id,
        "url": inputs.get("page_url") or meta.get("url") or "",
        "page_type": page.get("type") or meta.get("page_type") or "",
        "executive_summary": "",
        "ethics_summary": "",
    }


def _engagement_id(engagement_dir: Path, meta: dict[str, Any] | None) -> str:
    return (meta or {}).get("engagement_id") or engagement_dir.name


def _slide_id(device: str, slide_index: Any) -> str:
    return f"{device}-section-{int(slide_index) + 1}"


def _slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")


def _draft_artifact(device: str) -> str:
    return "visual-report-v2.html" if device == "laptop" else f"visual-report-{device}-v2.html"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _final_report_css() -> str:
    return """
:root{color-scheme:dark;--bg:#0d0f10;--panel:#161817;--ink:#f4efe3;--muted:#a9aa9f;--gold:#facc15;--line:#2b2e2a}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 20% 0,#262112,#0d0f10 38%,#080909);color:var(--ink);font:16px/1.5 Georgia,serif}
.hero{padding:42px clamp(20px,4vw,64px) 24px}.eyebrow{color:var(--gold);letter-spacing:.16em;text-transform:uppercase;font:700 12px/1 sans-serif}
h1{max-width:980px;margin:.2em 0;font-size:clamp(32px,5vw,68px);line-height:.95}main{display:grid;grid-template-columns:minmax(220px,320px) 1fr;gap:24px;padding:0 clamp(20px,4vw,64px) 56px}
.summary{position:sticky;top:16px;align-self:start;background:rgba(22,24,23,.86);border:1px solid var(--line);border-radius:20px;padding:18px}.summary ol{list-style:none;padding:0;margin:0;counter-reset:findings}.summary li{counter-increment:findings;display:grid;grid-template-columns:14px 1fr;gap:10px;align-items:start;margin:0 0 14px;padding:0}.summary li::before{content:counter(findings) ".";position:absolute;margin-left:-22px;color:var(--muted);font:600 11px sans-serif}.summary .sev-dot{width:10px;height:10px;border-radius:50%;margin-top:5px;display:inline-block}.summary .row-body{display:flex;flex-direction:column;gap:2px}.summary .row-body strong{color:var(--ink);font:600 13px/1.35 sans-serif}.summary .row-meta{color:var(--muted);font:11px/1.4 sans-serif;text-transform:uppercase;letter-spacing:.06em}
.slides{display:grid;gap:28px}.slide-card{background:rgba(22,24,23,.82);border:1px solid var(--line);border-radius:24px;padding:16px;box-shadow:0 24px 80px #0008}.slide-heading{display:flex;justify-content:space-between;color:var(--muted);font:700 13px sans-serif;text-transform:uppercase;letter-spacing:.08em;margin:0 0 12px}
.slide-stage{position:relative;overflow:visible;border-radius:16px;background:#050505}.slide-canvas{position:relative;display:block;border-radius:16px;transform-origin:center}.slide-stage img{display:block;width:100%;height:auto;border-radius:16px}.marker-layer{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;overflow:visible}@keyframes markerGlowPulse{0%,100%{opacity:var(--glow-opacity,.72)}50%{opacity:calc(var(--glow-opacity,.72) * .38)}}.marker-glow{mix-blend-mode:screen;animation:markerGlowPulse 1.45s ease-in-out infinite;transform-box:fill-box;transform-origin:center}.spotlight-dim{pointer-events:none}.callout{position:absolute;z-index:4;background:#0d0f10e8;border:1px solid #facc1580;border-radius:14px;padding:12px;box-shadow:0 10px 34px #000b;font:14px/1.35 sans-serif}.callout strong{color:var(--gold)}.callout p{margin:.45em 0 0;color:#e7e1d1}.blur-effect{position:absolute;z-index:2;border:1px dashed #facc15;backdrop-filter:blur(var(--blur,8px));-webkit-backdrop-filter:blur(var(--blur,8px));mask-image:radial-gradient(ellipse at center,#000 calc(100% - var(--feather,18%)),transparent 100%);-webkit-mask-image:radial-gradient(ellipse at center,#000 calc(100% - var(--feather,18%)),transparent 100%);background:radial-gradient(ellipse at center,rgba(250,204,21,.10) 0%,rgba(250,204,21,.05) calc(100% - var(--feather,18%)),rgba(250,204,21,0) 100%)}.blur-outside-effect{position:absolute;z-index:2;pointer-events:none;backdrop-filter:blur(var(--blur,8px));-webkit-backdrop-filter:blur(var(--blur,8px));background:rgba(10,10,10,.04)}.blur-focus-effect{position:absolute;z-index:3;border:1px solid #facc1580;box-shadow:0 0 0 1px #facc152e}.dim-region-effect{position:absolute;z-index:2;background:rgba(0,0,0,var(--dim-opacity,.38));border:1px dashed #bd8cff}
.connector-line{stroke:#facc15b8;stroke-width:.35;stroke-dasharray:1.2 1.2;vector-effect:non-scaling-stroke}
@media (max-width:800px){main{grid-template-columns:1fr}.summary{position:relative}}
@media print{
  :root{color-scheme:light}
  body{background:#fff !important;color:#111 !important;font:11pt/1.4 Georgia,serif}
  .hero{padding:24px 0 16px;border-bottom:1px solid #ddd}
  .hero h1{color:#111;font-size:24pt}
  .eyebrow{color:#444}
  main{display:block;padding:0 16pt}
  .summary{position:static;background:#fafafa !important;border:1px solid #ddd;color:#111;break-inside:avoid;margin:16pt 0}
  .summary .row-body strong{color:#111}
  .summary .row-meta{color:#444}
  .slides{display:block}
  .slide-card{background:#fff !important;border:1px solid #ddd;box-shadow:none;color:#111;break-inside:avoid;page-break-inside:avoid;margin:0 0 16pt}
  .slide-heading{color:#444}
  .slide-stage{background:#fff}
  .callout{background:#fff !important;color:#111 !important;border:1px solid #999;box-shadow:none}
  .callout p{color:#222}
  .blur-effect,.blur-outside-effect{backdrop-filter:none;-webkit-backdrop-filter:none;background:rgba(0,0,0,.06);border:1px solid #999}
  .blur-focus-effect{border:1px solid #999}
  .spotlight-dim{fill-opacity:.35}
  .connector-line{stroke:#444;stroke-dasharray:none}
}
"""
