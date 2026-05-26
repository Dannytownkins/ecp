#!/usr/bin/env python3
"""DOM preprocessor — slice a captured DOM into per-cluster context files.

Reads `dom.html` + `baton.json` (or `dom-mobile.html` + `baton-mobile.json`
on mobile) from the engagement directory and writes one
`cluster-context-{cluster}-{device}.json` file per cluster listed in
`meta.json` → `clusters_used`.

Each cluster-context file contains: per-section DOM slices relevant to the
cluster, the full page `<head>` (meta tags, schema, canonical), the
`<header>` + `<footer>` HTML (included in every cluster per the
contracts/dom-preprocessor.md global-section rule), filtered baton elements, styles,
and structured data.

Promoted to a first-class script in v1.0.1 per the 2026-04-14 postmortem —
previously the algorithm lived only in `contracts/dom-preprocessor.md` as
an example snippet, forcing every lead to reimplement it inline.

Usage
-----

    python scripts/dom_preprocess.py --engagement docs/ecp/{id} --device desktop
    python scripts/dom_preprocess.py --engagement docs/ecp/{id} --device mobile

On dual-device runs, invoke twice (once per device). The two runs are
independent — each reads its own DOM + baton file.

Skip conditions
---------------
- File-path mode (`source_mode: "file"` in meta.json) — no DOM to slice.
- Description mode (`source_mode: "description"`) — no DOM to slice.
- Screenshot-only mode (`source_mode: "screenshot"`) — no DOM to slice.

The script exits 0 with a single info line in those cases.

Empty-slice rule
----------------
If no baton sections route to a cluster AND the cluster's keyword fallback
produces no global-section matches, no context file is written. The lead's
expected_auditor_count should decrement accordingly.
"""
from __future__ import annotations

import argparse
import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from report.geometry import (
    element_rect_css,
    infer_element_coord_scale,
    section_scroll_bottom,
    section_scroll_top,
    viewport_dpr,
)

CLUSTERS_DEFAULT = [
    "visual-cta",
    "trust-credibility",
    "pricing",
    "checkout-flows",
    "performance-ux",
    "product-media",
    "category-navigation",
    "content-seo",
    "post-purchase",
    "audience",
]

# Max bytes of DOM slice per section — prevents single huge sections from
# blowing the auditor's context. Auditors work primarily from screenshots +
# filtered baton elements; the DOM slice is supporting evidence.
SECTION_SLICE_CAP = 80_000
HEAD_SLICE_CAP = 40_000
HEADER_SLICE_CAP = 40_000
FOOTER_SLICE_CAP = 40_000

# Cluster keyword routing (v2: PRIMARY source-of-truth, was fallback in v1).
# As of schema_version=3 (v2-architecture), these keyword rules are authoritative
# for which sections route to which clusters. The acquirer's
# baton.sections[].clusters array is advisory only in v2 — pinning the routing
# to code eliminates the cross-device variance documented in §22.1 #2 / §23.2 #2
# / §24.2 #3 where the LLM emitted different cluster arrays per device on
# identical DOM. Same template, same route, every run.
#
# Matches the rules documented in contracts/dom-preprocessor.md + the audit
# skill's `<phase_audit>` "Section-to-cluster routing (v2)" block.
_KEYWORDS = {
    "visual-cta": ["cta", "hero", "headline", "banner", "image", "carousel", "slide"],
    "trust-credibility": ["review", "trust", "badge", "social-proof", "ugc", "testimonial"],
    "pricing": ["price", "pricing", "discount", "shipping", "scarcity", "bundle", "bnpl"],
    "checkout-flows": ["checkout", "cart", "payment", "form", "consent"],
    "product-media": ["gallery", "thumbnail", "video", "ar", "image-quality", "product"],
    "category-navigation": [
        "search", "filter", "sort", "pagination", "breadcrumb", "category",
        "collection", "nav", "multicolumn", "menu",
    ],
    "content-seo": ["schema", "canonical", "seo", "meta", "sitemap", "head", "richtext"],
    "post-purchase": [
        "order-confirmation", "post-purchase", "loyalty", "referral",
        "newsletter", "footer",
    ],
    "audience": ["personalization", "cross-cultural", "social-commerce", "audience"],
    "performance-ux": ["performance", "lcp", "cls", "cwv", "speed", "mobile", "cognitive-load", "page-load"],
}

# Labels that are always routed to every cluster (header, footer, announcement
# bar, nav, above-fold). Documented in contracts/dom-preprocessor.md step 5.
_GLOBAL_LABEL_TOKENS = ("header", "footer", "announcement", "nav")


class _SectionExtractor(HTMLParser):
    """Pull shopify-section + <header> + <footer> + <head> out of the DOM."""

    _CONTAINER_TAGS = frozenset({
        "section", "div", "article", "main", "aside", "nav", "header",
        "footer", "form", "ul", "ol", "table", "details", "dialog",
        "fieldset", "figure",
    })
    _VOID_TAGS = frozenset({
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr",
    })

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.sections: dict[str, str] = {}
        self.current_section: str | None = None
        self.depth = 0
        self.buffer: list[str] = []
        self.header_html = ""
        self.footer_html = ""
        self.head_html = ""
        self._in_header = False
        self._in_footer = False
        self._in_head = False
        self._header_depth = 0
        self._footer_depth = 0

    def _section_label(self, classes: str) -> str:
        lc = classes.lower()
        for kw, name in [
            ("slideshow", "hero"),
            ("image-banner", "hero"),
            ("hero", "hero"),
            ("banner", "hero"),
            ("multicolumn", "category_nav"),
            ("featured-collection", "featured_collection"),
            ("featured_", "featured_collection"),
            ("collection-list", "featured_collection"),
            ("newsletter", "newsletter"),
            ("rich-text", "richtext"),
            ("announcement", "announcement"),
        ]:
            if kw in lc:
                return name
        return "unknown"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        classes = attrs_dict.get("class") or ""
        raw = self.get_starttag_text() or f"<{tag}>"

        if tag == "head":
            self._in_head = True
            self.head_html = raw
            return
        if self._in_head:
            self.head_html += raw
            return

        if tag == "header" and not self._in_header:
            self._in_header = True
            self._header_depth = 1
            self.header_html = raw
            return
        if self._in_header:
            if tag not in self._VOID_TAGS:
                self._header_depth += 1
            self.header_html += raw
            return

        if tag == "footer" and not self._in_footer:
            self._in_footer = True
            self._footer_depth = 1
            self.footer_html = raw
            return
        if self._in_footer:
            if tag not in self._VOID_TAGS:
                self._footer_depth += 1
            self.footer_html += raw
            return

        if tag == "section" and "shopify-section" in classes:
            base = self._section_label(classes)
            label = base
            i = 1
            while label in self.sections:
                i += 1
                label = f"{base}_{i}"
            self.current_section = label
            self.depth = 1
            self.buffer = [raw]
            self.sections[label] = ""  # reserve slot
            return

        if self.current_section is not None:
            if tag in self._CONTAINER_TAGS and tag not in self._VOID_TAGS:
                self.depth += 1
            self.buffer.append(raw)

    def handle_endtag(self, tag: str) -> None:
        if self._in_head:
            self.head_html += f"</{tag}>"
            if tag == "head":
                self._in_head = False
            return
        if self._in_header:
            self.header_html += f"</{tag}>"
            if tag not in self._VOID_TAGS:
                self._header_depth -= 1
            if self._header_depth <= 0:
                self._in_header = False
            return
        if self._in_footer:
            self.footer_html += f"</{tag}>"
            if tag not in self._VOID_TAGS:
                self._footer_depth -= 1
            if self._footer_depth <= 0:
                self._in_footer = False
            return

        if self.current_section is not None:
            self.buffer.append(f"</{tag}>")
            if tag == "section":
                self.depth -= 1
                if self.depth <= 0:
                    self.sections[self.current_section] = "".join(self.buffer)
                    self.current_section = None
                    self.buffer = []
            elif tag in self._CONTAINER_TAGS and tag not in self._VOID_TAGS:
                self.depth -= 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        raw = self.get_starttag_text() or f"<{tag}/>"
        if self._in_head:
            self.head_html += raw
        elif self._in_header:
            self.header_html += raw
        elif self._in_footer:
            self.footer_html += raw
        elif self.current_section is not None:
            self.buffer.append(raw)

    def handle_data(self, data: str) -> None:
        if self._in_head:
            self.head_html += data
        elif self._in_header:
            self.header_html += data
        elif self._in_footer:
            self.footer_html += data
        elif self.current_section is not None:
            self.buffer.append(data)


def _route_clusters_for(label: str) -> list[str]:
    """Determine cluster tags for a baton section from its label (v2 primary routing).

    Replaces v1's `_fallback_clusters_for`. In v2 (schema_version=3), the keyword-
    based result returned here is AUTHORITATIVE — the acquirer's
    baton.sections[].clusters array is no longer consulted as the primary source.
    See contracts/dom-preprocessor.md and skills/audit/SKILL.md `<phase_audit>`
    Section-to-cluster routing (v2) block.

    Returns the matched cluster slugs, or the default fallback set
    ['visual-cta', 'content-seo'] when no keyword matches (degraded but
    deterministic; do NOT route to all 10 clusters as v1 did).
    """
    lc = (label or "").lower()
    out: list[str] = []
    for cluster, tokens in _KEYWORDS.items():
        if any(tok in lc for tok in tokens):
            out.append(cluster)
    return out or ["visual-cta", "content-seo"]


# Backward compat alias for v1 callers during migration. Schedule for removal
# in v2.1 once all consumers reference _route_clusters_for directly.
_fallback_clusters_for = _route_clusters_for


def _is_global(label: str, scroll_y: int) -> bool:
    lc = (label or "").lower()
    if any(tok in lc for tok in _GLOBAL_LABEL_TOKENS):
        return True
    return scroll_y == 0


def _pick_dom_slice(section_label: str, extracted: dict[str, str]) -> str:
    lc = section_label.lower()
    # Direct match first
    for key, html in extracted.items():
        if key == "unknown":
            continue
        if key.replace("_", " ") in lc or key.replace("_", "") in lc:
            return html
    # Keyword-based
    if "hero" in lc or "banner" in lc:
        return extracted.get("hero", "")
    if "category" in lc or "multicolumn" in lc:
        return extracted.get("category_nav", "")
    if "featured" in lc or "collection" in lc or "product grid" in lc:
        return extracted.get("featured_collection", "")
    if "newsletter" in lc:
        return extracted.get("newsletter", "")
    if "announcement" in lc:
        return extracted.get("announcement", "")
    return ""


def preprocess_device(
    engagement_dir: Path,
    device: str,
    clusters: list[str],
) -> dict[str, int]:
    """Slice dom + baton for one device; return {"written": N, "skipped": M}."""
    suffix = "-mobile" if device == "mobile" else ""
    dom_path = engagement_dir / f"dom{suffix}.html"
    baton_path = engagement_dir / f"baton{suffix}.json"

    if not dom_path.exists() or not baton_path.exists():
        print(
            f"[{device}] skip - expected {dom_path.name} + {baton_path.name} not found",
            file=sys.stderr,
        )
        return {"written": 0, "skipped": len(clusters)}

    dom_html = dom_path.read_text(encoding="utf-8", errors="replace")
    baton = json.loads(baton_path.read_text(encoding="utf-8"))
    baton_sections = baton.get("sections", [])
    elements = baton.get("elements", [])
    styles = baton.get("styles", {})
    baton_page_head = baton.get("page_head") or {}
    structured_data = (
        baton_page_head.get("schema_jsonld")
        if isinstance(baton_page_head, dict)
        else None
    ) or baton.get("structured_data", [])
    viewport = baton.get("viewport", {})

    # Normalize element coordinates to CSS pixels for cluster-context
    # consumers. Auditors read the context; quoting screenshot-pixel
    # coordinates (e.g., "Add-to-Cart at y=2454") in their titles and
    # observations is meaningless to a store operator who measures their
    # page in CSS px. The original baton keeps screenshot pixels so the
    # renderer's hotspot-mapping math (which targets image coordinates)
    # stays correct.
    coord_scale = infer_element_coord_scale(
        elements,
        baton.get("screenshots") or [],
        viewport,
        viewport_dpr(viewport),
        baton_sections,
    )
    normalized_elements = []
    for el in elements:
        rect = element_rect_css(el, coord_scale)
        if rect is None:
            continue
        normalized_elements.append({
            **el,
            "x": round(rect["x"]),
            "y": round(rect["y"]),
            "width": round(rect["width"]),
            "height": round(rect["height"]),
            "rect": {
                **(el.get("rect") if isinstance(el.get("rect"), dict) else {}),
                "x": round(rect["x"]),
                "y": round(rect["y"]),
                "width": round(rect["width"]),
                "height": round(rect["height"]),
            },
            "coords": "css",
        })
    elements = normalized_elements

    extractor = _SectionExtractor()
    try:
        extractor.feed(dom_html)
        extractor.close()
    except Exception as exc:  # noqa: BLE001 — intentionally broad
        print(f"[{device}] parser error: {exc}", file=sys.stderr)

    extracted = {k: v for k, v in extractor.sections.items() if isinstance(v, str) and v}
    print(
        f"[{device}] extracted {len(extracted)} shopify-sections, "
        f"header {len(extractor.header_html)}B, "
        f"footer {len(extractor.footer_html)}B, "
        f"head {len(extractor.head_html)}B"
    )

    written = 0
    skipped = 0

    for cluster in clusters:
        cluster_sections: list[dict[str, Any]] = []
        seen_keys: set[tuple[int, str]] = set()

        for sec in baton_sections:
            label = sec.get("label") or ""
            scroll_y = int(section_scroll_top(sec))
            scroll_y_bottom = int(section_scroll_bottom(sec, float((viewport or {}).get("height") or 0)))
            # v2 routing precedence: deterministic Python keyword rules are PRIMARY,
            # baton's LLM-emitted clusters[] is advisory only. Closes §22.1 #2 / §23.2 #2
            # / §24.2 #3 cross-device routing inconsistency.
            section_clusters = _route_clusters_for(label) or sec.get("clusters") or ["visual-cta", "content-seo"]
            is_global = _is_global(label, scroll_y)

            if not (is_global or cluster in section_clusters):
                continue

            key = (scroll_y, label)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            dom_slice = _pick_dom_slice(label, extracted)
            if "footer" in label.lower():
                dom_slice = extractor.footer_html
            elif "header" in label.lower() or ("nav" in label.lower() and scroll_y < 100):
                dom_slice = extractor.header_html

            cluster_sections.append({
                "label": label,
                "scrollY": scroll_y,
                "height": max(1, scroll_y_bottom - scroll_y),
                "scroll_y_bottom": scroll_y_bottom,
                "clusters": section_clusters,
                "is_global": is_global,
                "dom_slice": dom_slice[:SECTION_SLICE_CAP] if dom_slice else "",
            })

        if not cluster_sections:
            print(f"[{device}] SKIP {cluster} - no sections routed")
            skipped += 1
            continue

        # Filter baton elements to those overlapping a cluster section (or global).
        cluster_elements = []
        for el in elements:
            rect = element_rect_css(el, 1.0) or {}
            ey = int(rect.get("y", 0) or 0)
            eh = int(rect.get("height", 0) or 0)
            for sec in cluster_sections:
                sy = sec.get("scrollY") or 0
                sh = sec.get("height") or 0
                if sec["is_global"] or (ey + eh >= sy and ey <= sy + sh):
                    cluster_elements.append(el)
                    break

        out = {
            "cluster": cluster,
            "device": device,
            "sections": cluster_sections,
            "page_head": extractor.head_html[:HEAD_SLICE_CAP],
            "page_head_html": extractor.head_html[:HEAD_SLICE_CAP],
            "baton_page_head": baton_page_head,
            "header_html": extractor.header_html[:HEADER_SLICE_CAP],
            "footer_html": extractor.footer_html[:FOOTER_SLICE_CAP],
            "elements": cluster_elements,
            "coords": "css",  # element x/y/width/height are in CSS pixels, DPR-normalized
            "styles": styles,
            "structured_data": structured_data,
            "viewport": viewport,
        }
        out_path = engagement_dir / f"cluster-context-{cluster}-{device}.json"
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        size = out_path.stat().st_size
        print(
            f"[{device}] wrote {out_path.name} ({size:,}B, "
            f"{len(cluster_sections)} sections, {len(cluster_elements)} elements)"
        )
        written += 1

    return {"written": written, "skipped": skipped}


def _resolve_clusters(engagement_dir: Path) -> list[str]:
    meta_path = engagement_dir / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        clusters = meta.get("clusters_used") or []
        if clusters:
            return clusters
    return CLUSTERS_DEFAULT


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Slice a captured DOM into per-cluster context files (ECP v1.0.1)."
    )
    ap.add_argument(
        "--engagement",
        required=True,
        type=Path,
        help="Path to engagement directory (containing dom.html + baton.json).",
    )
    ap.add_argument(
        "--device",
        required=True,
        choices=["mobile", "laptop", "desktop"],
        help="Which device's DOM to slice.",
    )
    ap.add_argument(
        "--clusters",
        default=None,
        help="Comma-separated cluster list (overrides meta.json clusters_used).",
    )
    args = ap.parse_args(argv)

    engagement_dir: Path = args.engagement
    if not engagement_dir.exists():
        print(f"ERROR: engagement dir not found: {engagement_dir}", file=sys.stderr)
        return 2

    # Honor skip conditions from meta.json
    meta_path = engagement_dir / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        source_mode = meta.get("source_mode") or ""
        if source_mode in ("file", "description", "screenshot"):
            print(f"[{args.device}] skip - source_mode={source_mode!r} has no DOM to slice")
            return 0

    if args.clusters:
        clusters = [c.strip() for c in args.clusters.split(",") if c.strip()]
    else:
        clusters = _resolve_clusters(engagement_dir)

    result = preprocess_device(engagement_dir, args.device, clusters)
    print(
        f"[{args.device}] done - wrote {result['written']} context files, "
        f"skipped {result['skipped']} empty clusters"
    )

    # Phase 4a hardening (2026-05-18) — write anchor-candidates-{device}.json
    # alongside the cluster contexts so specialists dispatched after
    # preprocessing have a ready-made registry to cite via candidate_id.
    # Skipped silently when the baton is missing (file-mode engagements
    # may not have one).
    baton_filename = (
        "baton.json" if args.device in {"desktop", "laptop"}
        else f"baton-{args.device}.json"
    )
    if (engagement_dir / baton_filename).exists():
        from assembly.anchor_candidates import build_anchor_candidates_sidecar
        try:
            sidecar = build_anchor_candidates_sidecar(engagement_dir, args.device)
            print(
                f"[{args.device}] anchor-candidates written: "
                f"{sidecar['counts']['total_candidates']} candidates across "
                f"{len(sidecar['candidates_by_role'])} roles "
                f"(from {sidecar['counts']['baton_elements']} baton elements)"
            )
        except Exception as exc:  # pragma: no cover — best-effort sidecar
            print(
                f"[{args.device}] WARNING: anchor-candidates sidecar build failed: {exc}",
                file=sys.stderr,
            )
    else:
        print(f"[{args.device}] anchor-candidates skipped - {baton_filename} not present")

    return 0


if __name__ == "__main__":
    # Ensure scripts/ is on sys.path so dom_preprocess can import sibling
    # modules (assembly.anchor_candidates) when run as a standalone script.
    if str(Path(__file__).resolve().parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(main())
