"""Orchestration: generate_report() and helpers."""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from .utils import (
    aspect_ratio_value,
    get_severity_class,
    get_device_frame_css,
)
from .parser import (
    parse_findings,
    parse_priority_path,
    parse_sources,
)
from .citations import is_safe_citation_url, resolve_citation_url, humanize_reference
from .markers import auto_map_markers, compute_marker_positions
from .images import encode_image_base64
from .path_safety import resolve_within_base
from .templates.components import (
    # v1.0 three-panel app shell builders
    assign_cluster_indices,
    build_clusters_tab_html,
    build_priority_tab_html,
    build_ethics_tab_html,
    build_detail_panels_html,
    build_hotspot_overlays_html,
    build_export_markdown_blocks,
    # legacy + shared helpers (severity + ethics summary still used in header)
    build_severity_bars,
    build_severity_text_html,
    build_ethics_html,
)
from .templates.html_structure import assemble_html


def _synth_stories_to_render_shape(stories):
    """Convert validated synthesizer Story objects to the shape the
    priority-tab renderer expects (the same shape parse_priority_path
    emits from markdown).

    Synthesizer Story keys:
        title, severity, narrative_md, action_md, f_refs

    Renderer shape (from parse_priority_path):
        number, title, severity, fixes_count, spans_clusters,
        description, action, underlying=[{cluster, index, label}]

    Splits ``"{cluster} F-{NN}"`` f_refs into structured underlying
    entries. Skips malformed refs defensively — the synthesizer
    validator should have rejected them upstream, but a defensive skip
    here means the render path never raises on sidecar parsing.
    """
    import re as _re
    out = []
    for i, story in enumerate(stories, start=1):
        underlying = []
        for ref in story.get("f_refs") or []:
            m = _re.match(r"^([\w-]+)\s+F-(\d+)$", str(ref))
            if not m:
                continue
            cluster = m.group(1)
            idx = int(m.group(2))
            underlying.append({
                "cluster": cluster,
                "index": idx,
                "label": ref,
            })
        spans_clusters = sorted({u["cluster"] for u in underlying})
        out.append({
            "number": str(i),
            "title": story.get("title", ""),
            "severity": (story.get("severity") or "MEDIUM").upper(),
            "fixes_count": len(underlying),
            "spans_clusters": spans_clusters,
            "description": (story.get("narrative_md") or "").strip(),
            "action": (story.get("action_md") or "").strip(),
            "underlying": underlying,
        })
    return out


def _load_priority_path_stories(engagement_path, device, audit_file):
    """Load Priority Path stories with sidecar-first preference.

    Read order (H1 fix — prevents stale-markdown drift):

    1. ``priority-path-stories{suffix}.json`` — the validated synthesizer
       output written by ``assembly.writer.write_sidecars``. This is the
       source of truth because it was produced under
       ``synthesizer_parser.validate_stories`` — every F-N ref is in the
       allowlist, every story structure passed schema checks.

    2. Markdown fallback — ``parse_priority_path(audit.md)``. Used when
       the sidecar is absent, which happens for legacy engagements
       predating this sidecar or when ``assemble-audit.py`` was run
       without ``--priority-path``. Parsing markdown is looser than the
       sidecar (can't detect F-N refs invented by a hand-editor), but
       it's the only option when no sidecar exists.

    Sidecar filename convention mirrors ``writer._sidecar_suffix``:
    laptop uses bare ``priority-path-stories.json``, others use
    ``priority-path-stories-{device}.json``.
    """
    suffix = "" if device == "laptop" else f"-{device}"
    sidecar_path = engagement_path / f"priority-path-stories{suffix}.json"
    if sidecar_path.exists():
        try:
            with open(sidecar_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            stories = payload.get("stories") if isinstance(payload, dict) else None
            if isinstance(stories, list) and stories:
                return _synth_stories_to_render_shape(stories)
        except (OSError, IOError, json.JSONDecodeError):
            # Fall through to markdown parse — sidecar is present but
            # unreadable or malformed. Log-via-stderr would be nicer
            # but the existing code path doesn't log at this layer.
            pass
    return parse_priority_path(engagement_path / audit_file)


def _load_inputs(engagement_path, baton_file, audit_file, plugin_path, device):
    """Load plugin version, baton, meta, findings, pass findings, and priority path.

    ``device`` is used to pick the correct ``priority-path-stories`` sidecar
    filename (laptop uses bare, others use device-tagged). See
    ``_load_priority_path_stories`` for the sidecar-first load order.
    """
    plugin_version = "unknown"
    manifest_candidates = [
        plugin_path / ".codex-plugin" / "plugin.json",
        plugin_path / ".claude-plugin" / "plugin.json",
    ]
    for plugin_manifest in manifest_candidates:
        if plugin_manifest.exists():
            with open(plugin_manifest, "r", encoding="utf-8") as f:
                plugin_version = json.load(f).get("version", plugin_version)
            break

    with open(engagement_path / baton_file, "r", encoding="utf-8") as f:
        baton = json.load(f)

    meta_path = engagement_path / "meta.json"
    meta = {}
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

    findings = parse_findings(engagement_path / audit_file)
    priority_path_stories = _load_priority_path_stories(engagement_path, device, audit_file)

    # Extract the audited page URL so downstream stages (e.g., the ethics
    # SOURCE_URL integrity check in _resolve_citations) can detect when
    # an ethics citation misleadingly points back at the store.
    _page = meta.get("page") or {}
    page_url = (
        _page.get("url")
        or meta.get("url")
        or meta.get("url_normalized")
        or None
    )

    return {
        "plugin_version": plugin_version,
        "baton": baton,
        "meta": meta,
        "page_url": page_url,
        "findings": findings,
        "priority_path_stories": priority_path_stories,
    }


def _resolve_citations(findings, plugin_path, page_url=None):
    """Resolve citation URLs into findings (in place).

    Preserves an existing source_url (populated from SOURCE_URL: in the
    finding's cluster-file block via report/parser.py) before falling back
    to the citations/sources.md lookup. Critical for ethics findings, which
    carry their own primary-source URL and should not be overwritten by a
    weaker reference-file match.

    Every URL — whether from the finding's SOURCE_URL field or from the
    sources lookup — is validated against ``is_safe_citation_url`` before
    it reaches the renderer. Unsafe URLs (javascript:, data:, private IPs,
    control chars, overlong) are cleared; the finding renders as
    ``(source unavailable)`` instead of a click-to-execute XSS vector.

    Ethics-finding source URL integrity check (2026-04-21):
    If a finding has ``ETHICS_STATE: ADJACENT`` or ``ETHICS_STATE: BLOCK``
    AND its ``source_url`` resolves to the same domain as the audited
    ``page_url``, clear ``source_url`` to None. Rationale: an ethics
    citation (FTC regulation, EU Directive, FDA rule) must link to the
    law or canonical standard — NOT back to the store being audited. The
    prior behavior silently rendered the product URL as if it were the
    source of the ePrivacy Directive, which reads as fabricated evidence.
    Clearing the field forces the renderer to fall through to the
    reference-file lookup or show "(source unavailable)" — both more
    honest than a misleading same-domain link.
    """
    from urllib.parse import urlparse
    page_netloc = None
    if page_url:
        try:
            parsed_page = urlparse(page_url)
            if parsed_page.scheme in ("http", "https") and parsed_page.netloc:
                page_netloc = parsed_page.netloc.lower().lstrip("www.")
        except ValueError:
            page_netloc = None

    sources_lookup = parse_sources(plugin_path)
    for f in findings:
        ethics_state = (f.get("ethics_state") or "").upper()
        is_ethics_finding = ethics_state in ("ADJACENT", "BLOCK")

        if f.get("source_url"):
            # Safety check first.
            if not is_safe_citation_url(f["source_url"]):
                f["source_url"] = None
                continue

            # Ethics-finding integrity: an ethics citation MUST NOT
            # point back at the audited store. Flag and clear.
            if is_ethics_finding and page_netloc:
                try:
                    src_netloc = urlparse(f["source_url"]).netloc.lower().lstrip("www.")
                    if src_netloc == page_netloc:
                        print(
                            f"warning: ethics finding (index={f.get('index')}) had "
                            f"SOURCE_URL pointing at the audited domain "
                            f"({src_netloc}) - cleared to force fallback. The "
                            f"cluster file should cite the regulation's canonical "
                            f"URL from ethics-gate.md Source Registry, not the "
                            f"page under audit.",
                            file=sys.stderr,
                        )
                        f["source_url"] = None
                        continue
                except ValueError:
                    pass
            continue
        url = resolve_citation_url(f.get("citation", ""), sources_lookup)
        if not url:
            url = resolve_citation_url(f.get("reference", ""), sources_lookup)
        if url and is_safe_citation_url(url):
            f["source_url"] = url


def _build_marker_mappings(findings, baton, markers_file):
    """Load or auto-generate marker mappings and compute pixel positions."""
    markers_mapping = []
    if markers_file and os.path.exists(markers_file):
        with open(markers_file, "r", encoding="utf-8") as f:
            markers_mapping = json.load(f)
    elif not markers_file:
        markers_mapping = auto_map_markers(findings, baton)
    slide_markers = compute_marker_positions(markers_mapping, baton)
    return markers_mapping, slide_markers


def _load_review_state(review_state_file, engagement_path):
    if not review_state_file:
        return None
    review_path = Path(review_state_file)
    if not review_path.is_absolute():
        review_path = engagement_path / review_path
    try:
        with open(review_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, IOError, json.JSONDecodeError):
        return None
    return state if isinstance(state, dict) else None


def _review_override_enabled(review_finding):
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


def _review_effects_by_ref(review_state):
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
    effects_by_ref = {}
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


def _review_float(value, default):
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _apply_review_state_to_findings(findings, review_state):
    review_by_ref = {
        f.get("f_ref"): f
        for f in review_state.get("findings", [])
        if isinstance(f, dict) and f.get("f_ref")
    }
    effects_by_ref = _review_effects_by_ref(review_state)
    for finding in findings:
        ref = _finding_review_ref(finding)
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


def _finding_review_ref(finding):
    ref = finding.get("f_ref")
    if ref:
        return ref
    fid = finding.get("fid")
    if fid and "/" in fid:
        cluster, number = fid.rsplit("/", 1)
        return f"{cluster} {number}"
    cluster = finding.get("cluster")
    idx = finding.get("cluster_index")
    if cluster and idx:
        return f"{cluster} F-{int(idx):02d}"
    return None


def _apply_review_state_to_slide_markers(slide_markers, review_state, findings):
    slide_id_to_idx = {
        slide.get("slide_id"): idx
        for idx, slide in enumerate(review_state.get("slides", []))
        if isinstance(slide, dict) and slide.get("slide_id")
    }
    findings_by_ref = {
        _finding_review_ref(f): f
        for f in findings
        if _finding_review_ref(f)
    }
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
    active_indices = {
        findings_by_ref[ref].get("index")
        for ref in markers_by_ref
        if ref in findings_by_ref
    }
    for slide_idx, markers in slide_markers.items():
        kept = [
            m for m in markers
            if m.get("f_ref") not in markers_by_ref
            and m.get("finding_index") not in active_indices
        ]
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
        }
        if w >= 1 and h >= 1:
            left = max(0.0, min(100.0, x))
            top = max(0.0, min(100.0, y))
            out["zone"] = {
                "left_pct": left,
                "top_pct": top,
                "w_pct": max(0.0, min(100.0 - left, w)),
                "h_pct": max(0.0, min(100.0 - top, h)),
            }
        patched.setdefault(slide_idx, []).append(out)

    return patched


def _process_screenshots(engagement_path, baton, slide_markers):
    """Base64-encode screenshots (hotspots are rendered as interactive overlays)."""
    viewport = baton.get("viewport", {})
    default_slide_aspect_ratio = aspect_ratio_value(viewport.get("width"), viewport.get("height"))
    screenshots = baton.get("screenshots", [])
    screenshot_paths = []
    for ss in screenshots:
        if isinstance(ss, dict):
            screenshot_paths.append(ss.get("path", ss.get("file", "")))
        elif isinstance(ss, str):
            screenshot_paths.append(ss)

    slide_base64 = []
    slide_aspect_ratios = []
    for i, ss_path in enumerate(screenshot_paths):
        # Path containment: reject baton-supplied screenshot paths that
        # escape the engagement directory. A crafted baton.json with
        # "path": "../../../etc/passwd" would otherwise base64-embed an
        # arbitrary local file into a customer-facing report. resolve_within_base
        # follows symlinks and normalizes .. components before the containment
        # check, so both relative and absolute escape attempts are caught.
        try:
            full_path = resolve_within_base(ss_path, engagement_path)
        except ValueError as exc:
            print(
                f"ERROR: baton screenshot path rejected (path traversal): {exc}",
                file=sys.stderr,
            )
            sys.exit(2)
        if not full_path.exists():
            continue

        screenshot_meta = screenshots[i] if i < len(screenshots) and isinstance(screenshots[i], dict) else {}
        slide_aspect_ratios.append(
            aspect_ratio_value(
                screenshot_meta.get("naturalWidth") or screenshot_meta.get("width") or viewport.get("width"),
                screenshot_meta.get("naturalHeight") or screenshot_meta.get("height") or viewport.get("height"),
                default_slide_aspect_ratio,
            )
        )

        slide_base64.append(encode_image_base64(str(full_path)))

    if not slide_base64:
        # Codex M3 — previously this was a hard sys.exit(1). Now we degrade
        # gracefully: file-mode audits don't have screenshots, description-
        # mode audits don't have screenshots, and URL-mode acquisition
        # failures shouldn't take down the whole render. The findings,
        # Priority Path, ethics tab, and detail panels all work without
        # screenshots. The JS runtime's setSlide() early-returns when
        # SLIDE_SOURCES is empty, so the empty array flows through the
        # rest of the pipeline safely.
        print(
            "Notice: no screenshots available - rendering text-only report. "
            "Findings + Priority Path + ethics tab will still render; the "
            "center screenshot panel will show the empty-state placeholder.",
            file=sys.stderr,
        )

    return {
        "slide_base64": slide_base64,
        "slide_aspect_ratios": slide_aspect_ratios,
        "default_slide_aspect_ratio": default_slide_aspect_ratio,
    }


def _compute_metrics(findings):
    """Count severities, compute evidence confidence, and projected lift."""
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        sev = get_severity_class(f.get("priority"))
        if sev in severity_counts:
            severity_counts[sev] += 1

    total_findings = sum(severity_counts.values())

    gold_silver = sum(1 for f in findings if f.get("tier", "").lower() in ("gold", "silver"))
    intent_reliability = round(gold_silver / max(total_findings, 1) * 100, 1)

    if total_findings == 0:
        evidence_confidence_label = "LOW"
        evidence_confidence_class = "critical"
    elif intent_reliability >= 70:
        evidence_confidence_label = "HIGH"
        evidence_confidence_class = "green"
    elif intent_reliability >= 40:
        evidence_confidence_label = "MEDIUM"
        evidence_confidence_class = "amber"
    else:
        evidence_confidence_label = "LOW"
        evidence_confidence_class = "critical"

    projected_lift = min(
        severity_counts["critical"] * 5
        + severity_counts["high"] * 3
        + severity_counts["medium"] * 1.5
        + severity_counts["low"] * 0.5,
        35,
    )

    return {
        "severity_counts": severity_counts,
        "total_findings": total_findings,
        "evidence_confidence_label": evidence_confidence_label,
        "evidence_confidence_class": evidence_confidence_class,
        "projected_lift": projected_lift,
    }


def _check_ethics(engagement_path, audit_file, findings):
    """Determine whether ethics violations exist."""
    has_ethics_violations = False
    try:
        with open(engagement_path / audit_file, "r", encoding="utf-8") as audit_fh:
            audit_text = audit_fh.read()
        ethics_header_match = re.search(
            r"^## Ethics Gate:\s*(.+?)$",
            audit_text,
            re.MULTILINE,
        )
        if ethics_header_match:
            ethics_status = ethics_header_match.group(1).strip().lower()
            has_ethics_violations = (
                "violation" in ethics_status
                or "fail" in ethics_status
                or "critical" in ethics_status
            )
    except (OSError, IOError):
        pass

    if not has_ethics_violations:
        has_ethics_violations = any(
            f.get("priority", "").lower() == "critical" and (
                "ethics" in (f.get("reference") or "").lower()
                or "ethics-gate" in (f.get("reference") or "").lower()
                or "ftc" in (f.get("observation") or "").lower()
                or "fake review" in (f.get("observation") or "").lower()
                or "dsa art" in (f.get("observation") or "").lower()
            )
            for f in findings
        )

    return has_ethics_violations


def _load_metadata(engagement_path, baton, meta, device, plugin_path):
    """Load font CSS and extract metadata strings."""
    font_path = plugin_path / "templates" / "font-embed.css"
    font_css = ""
    if font_path.exists():
        with open(font_path, "r", encoding="utf-8") as f:
            font_css = f.read()

    viewport = baton.get("viewport", {})
    device_label = f"{device.title()} ({viewport.get('width', '?')}\u00d7{viewport.get('height', '?')})"
    date_str = meta.get("created", "")[:10] if meta.get("created") else "Unknown"

    # Schema compatibility per 2026-04-14 codebase audit #2 / #14. Live writers
    # emit `engagement_id`, top-level `url`, and no `page.type`; the original
    # schema/template used `id`, `page.url`, `page.type`. Fall through both so
    # the header never renders "Unknown URL" when the URL is clearly present.
    page = meta.get("page") or {}
    engagement_id = meta.get("id") or meta.get("engagement_id") or engagement_path.name
    page_url = (
        page.get("url")
        or meta.get("url")
        or meta.get("url_normalized")
        or "Unknown URL"
    )
    page_type = (page.get("type") or meta.get("page_type") or "Unknown").title()
    platform = (meta.get("platform") or "Unknown").title()
    source_mode = meta.get("source_mode", "Unknown")
    generated_date = datetime.now().strftime("%Y-%m-%d")

    return {
        "font_css": font_css,
        "device_label": device_label,
        "date_str": date_str,
        "engagement_id": engagement_id,
        "page_url": page_url,
        "page_type": page_type,
        "platform": platform,
        "source_mode": source_mode,
        "generated_date": generated_date,
    }


def _build_html_fragments(findings, priority_path_stories,
                          slide_markers, metrics, has_ethics_violations,
                          screenshots, audit_md_text):
    """Build all HTML fragment strings used in the v1.0 three-panel report.

    Returns a dict of keys consumed by ``assemble_html(ctx)``. Contract:
    - ``clusters_tab_html``   — left rail "By Cluster" contents
    - ``priority_tab_html``   — left rail "Priority Path" contents
    - ``ethics_tab_html``     — left rail "Ethics" contents
    - ``detail_panels_html``  — right rail (all cards, hidden until selected)
    - ``hotspot_overlays_html`` — center-slide hotspot rects
    - ``findings_json``       — JSON payload consumed by the runtime JS
    - ``export_markdown_json`` — JSON array of {fid, block} for the markdown
                                 export mirror
    - plus the ethics header chip + severity metadata still used up top.

    The v5/v6 ``pass_findings``, ``cluster_finding_map``, and ``thumb_html``
    parameters/outputs were removed in v1.0.1 per the codebase audit — the
    app-shell no longer renders a thumbnail strip, What's-Working-Well pass
    list, or legacy cluster-map anchors.
    """
    severity_counts = metrics["severity_counts"]
    total_findings = metrics["total_findings"]

    # --- Assign cluster-scoped F-NN + fid to each finding --------------------
    findings_by_cluster, findings_by_fid = assign_cluster_indices(findings)
    clusters_count = len(findings_by_cluster)

    # --- Build clickable hotspot overlays (v1.0 zone rects) -----------------
    hotspot_overlays_html = build_hotspot_overlays_html(findings, slide_markers)

    # --- Left rail tabs -----------------------------------------------------
    clusters_tab_html = build_clusters_tab_html(findings_by_cluster)
    priority_tab_html = build_priority_tab_html(priority_path_stories, findings_by_fid)
    ethics_tab_html = build_ethics_tab_html(findings_by_fid)
    ethics_count = sum(
        1 for f in findings_by_fid.values()
        if (f.get("ethics_state") or "").upper() in ("BLOCK", "ADJACENT")
    )

    # --- Right rail detail cards --------------------------------------------
    detail_panels_html = build_detail_panels_html(findings)

    # --- JSON payloads for JS runtime ---------------------------------------
    findings_payload = []
    for f in findings:
        findings_payload.append({
            "fid": f["fid"],
            "f_ref": f.get("f_ref") or _finding_review_ref(f) or "",
            "cluster": f.get("cluster", ""),
            "cluster_index": f["cluster_index"],
            "short_code": f.get("short_code", ""),
            "priority": (f.get("priority") or "MEDIUM").upper(),
            "title": f["title"],
            "observation": f.get("observation", ""),
            "recommendation": f.get("recommendation", ""),
            "ethics_state": (f.get("ethics_state") or "").upper(),
            "review_status": f.get("_review_status"),
            "review_callout_title": f.get("review_callout_title"),
            "review_callout_body": f.get("review_callout_body"),
            "review_callout_color": f.get("review_callout_color"),
            "review_callout_position": f.get("review_callout_position"),
            "review_effects": f.get("review_effects") or [],
        })
    # JSON-in-HTML escape: any literal `</` inside a JSON string (most
    # importantly `</script>` in a Speculation Rules example or similar
    # HTML/script fragments cited in a finding) must be escaped as `<\/`
    # before embedding inside a `<script>` block. Otherwise the HTML
    # parser honors the `</script>` and closes the script tag early —
    # truncating the JS runtime. This was the root cause of the "desktop
    # clicks don't work" bug Dan flagged on 2026-04-14.
    def _safe_json(obj):
        return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--")

    findings_json = _safe_json(findings_payload)

    export_markdown_payload = build_export_markdown_blocks(findings, audit_md_text)
    export_markdown_json = _safe_json(export_markdown_payload)

    # --- Severity + ethics summary used by the header chip ------------------
    severity_bars = build_severity_bars(severity_counts)
    severity_inline_stats, severity_inline_segments, severity_text_html = build_severity_text_html(
        severity_counts, total_findings
    )
    ethics_main, ethics_main_class, ethics_note, ethics_icon, ethics_violation_detail_html = build_ethics_html(
        has_ethics_violations, findings
    )

    return {
        "hotspot_overlays_html": hotspot_overlays_html,
        "clusters_tab_html": clusters_tab_html,
        "priority_tab_html": priority_tab_html,
        "has_priority_path_stories": bool(priority_path_stories),
        "ethics_tab_html": ethics_tab_html,
        "detail_panels_html": detail_panels_html,
        "findings_json": findings_json,
        "export_markdown_json": export_markdown_json,
        "clusters_count": clusters_count,
        "ethics_count": ethics_count,
        "severity_bars": severity_bars,
        "severity_inline_stats": severity_inline_stats,
        "severity_inline_segments": severity_inline_segments,
        "severity_text_html": severity_text_html,
        "ethics_main": ethics_main,
        "ethics_main_class": ethics_main_class,
        "ethics_note": ethics_note,
        "ethics_icon": ethics_icon,
        "ethics_violation_detail_html": ethics_violation_detail_html,
    }


def _write_output(engagement_path, device, output_file, html, device_label,
                  total_findings, slide_base64, slide_markers):
    """Write the HTML report file and print CLI summary."""
    if not output_file:
        if device == "laptop":
            output_file = "visual-report.html"
        else:
            output_file = f"visual-report-{device}.html"

    output_path = engagement_path / output_file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    mapped = sum(len(m) for m in slide_markers.values())
    print(f"Report written to: {output_path}")
    print(f"  Device: {device_label}")
    print(f"  Findings: {total_findings}")
    print(f"  Screenshots: {len(slide_base64)}")
    print(f"  Marker positions mapped: {mapped}")
    print(f"  Click overlays: {mapped}")

    # Hotspot match-rate canary — fires when auditors emit vague ELEMENT
    # descriptors (e.g. "section.hero (above-fold area)", "body (homepage,
    # all sections)") that don't match any selector in baton.elements[].
    # Default-positioned markers look like "wrong placement" to operators.
    if total_findings:
        rate = mapped / total_findings
        if rate < 0.9:
            unmapped = total_findings - mapped
            print(
                f"  WARNING: hotspot match rate {mapped}/{total_findings} "
                f"({rate:.0%}) is below 90% - {unmapped} finding(s) placed "
                f"at fallback positions and may appear misaligned. Either "
                f"(a) re-prompt auditors to emit a real CSS selector that "
                f"appears in baton.elements[], or (b) supply --markers "
                f"<JSON> to manually pin those findings.",
                file=sys.stderr,
            )


def generate_report(
    engagement_dir,
    device,
    audit_file,
    baton_file,
    plugin_root,
    markers_file,
    output_file=None,
    review_state_file=None,
):
    """Generate the complete visual report HTML."""

    engagement_path = Path(engagement_dir)
    plugin_path = Path(plugin_root)

    # Phase 0a: Path containment on operator-supplied markers path. If
    # --markers is explicitly set, require it to live inside the engagement
    # directory. Central/shared marker files can be symlinked into place.
    # Read-only input, so the risk is embedding arbitrary JSON content
    # into the report runtime payload — containment check costs nothing.
    if markers_file:
        try:
            markers_file = str(resolve_within_base(markers_file, engagement_path))
        except ValueError as exc:
            print(
                f"ERROR: --markers path rejected (must live inside engagement dir): {exc}",
                file=sys.stderr,
            )
            sys.exit(2)

    # Phase 0b: Device pairing validation. Dual-device engagements produce
    # both audit.md (first device) and audit-{device}.md (others), plus
    # baton.json / baton-mobile.json. It's too easy to pair --audit audit.md
    # --device mobile when audit.md is actually the desktop audit. The
    # result is a report that claims "Mobile" in the header but shows
    # desktop findings against desktop screenshots. Codex Phase 1 flagged
    # the first-device-gets-bare-audit.md convention as a pairing-
    # ambiguity HIGH issue.
    #
    # We validate by reading the audit.md's declared device (either the
    # canonical **Viewport:** line emitted by writer.py or the **Device:**
    # line sometimes used in hand-written audits) and comparing to --device.
    # Mismatch → exit 4 with a clear pairing error.
    #
    # Graceful fallback: if the audit.md has no parseable device marker,
    # we don't block — older audits or unusual formats shouldn't hard-fail.
    audit_path = engagement_path / audit_file
    if audit_path.exists():
        try:
            audit_text_preview = audit_path.read_text(encoding="utf-8")[:2000]
        except (OSError, IOError):
            audit_text_preview = ""
        declared_device = None
        viewport_match = re.search(
            r"^\*\*Viewport:\*\*\s+(\w+)", audit_text_preview, re.MULTILINE,
        )
        if viewport_match:
            declared_device = viewport_match.group(1).lower()
        else:
            device_match = re.search(
                r"^\*\*Device:\*\*\s+(\w+)", audit_text_preview, re.MULTILINE,
            )
            if device_match:
                declared_device = device_match.group(1).lower().rstrip(",")
        if declared_device and declared_device != device.lower():
            print(
                f"ERROR: --device {device!r} does not match audit.md's "
                f"declared device ({declared_device!r}). Likely cause: "
                f"paired --audit {audit_file} with the wrong --device "
                "argument. For dual-device engagements, use "
                "--audit audit.md for the first device and "
                "--audit audit-{device}.md for the others. "
                "Check meta.json's devices_requested.",
                file=sys.stderr,
            )
            sys.exit(4)

    # Phase 1: Load inputs
    inputs = _load_inputs(engagement_path, baton_file, audit_file, plugin_path, device)
    review_state = _load_review_state(review_state_file, engagement_path)

    # Phase 2: Resolve citations (mutates findings in place)
    _resolve_citations(
        inputs["findings"],
        plugin_path,
        page_url=inputs.get("page_url"),
    )

    # Phase 2b: Assign cluster-scoped F-NN + fid BEFORE marker mapping so
    # hotspot numbering stays cluster-local and aligned across list/callout/UI.
    assign_cluster_indices(inputs["findings"])
    if review_state:
        _apply_review_state_to_findings(inputs["findings"], review_state)
        inputs["findings"] = [f for f in inputs["findings"] if not f.get("_review_hidden")]

    # Phase 3: Build marker mappings and process screenshots
    markers_mapping, slide_markers = _build_marker_mappings(
        inputs["findings"], inputs["baton"], markers_file
    )
    if review_state:
        slide_markers = _apply_review_state_to_slide_markers(
            slide_markers,
            review_state,
            inputs["findings"],
        )
    screenshots = _process_screenshots(
        engagement_path, inputs["baton"], slide_markers
    )

    # Phase 4: Compute metrics and check ethics
    metrics = _compute_metrics(inputs["findings"])
    has_ethics_violations = _check_ethics(engagement_path, audit_file, inputs["findings"])

    # Phase 5: Metadata
    metadata = _load_metadata(
        engagement_path, inputs["baton"], inputs["meta"], device, plugin_path
    )

    # Phase 6: Build HTML fragments (pass raw audit.md for markdown export mirror)
    audit_md_text = ""
    try:
        with open(engagement_path / audit_file, "r", encoding="utf-8") as _fp:
            audit_md_text = _fp.read()
    except (OSError, IOError):
        audit_md_text = ""
    fragments = _build_html_fragments(
        inputs["findings"], inputs["priority_path_stories"],
        slide_markers, metrics, has_ethics_violations, screenshots,
        audit_md_text,
    )

    # Phase 7: Assemble context and generate HTML
    has_screenshots = len(screenshots["slide_base64"]) > 0
    ctx = {
        **metadata, **metrics, **fragments,
        "plugin_version": inputs["plugin_version"],
        "device": device,
        # M3 — let the HTML assembler swap the empty-state hint when
        # rendering a text-only report (no screenshots acquired).
        "has_screenshots": has_screenshots,
        # slide sources are base64 data URIs but apply the same safety
        # replacement for defense-in-depth: any future base64 input that
        # happens to decode to a literal `</` byte sequence still stays
        # inside the script tag.
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

    # Phase 8: Write output
    _write_output(
        engagement_path, device, output_file, html,
        metadata["device_label"], metrics["total_findings"],
        screenshots["slide_base64"], slide_markers,
    )
