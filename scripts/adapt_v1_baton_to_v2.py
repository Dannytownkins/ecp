"""One-shot adapter: convert a v1 baton + cluster-context into a v2-shape baton.

Used during Phase B smoke testing only — lets the pricing specialist run
against an existing v1-engagement fixture without re-acquiring the page.
Phase A's updated workflows/acquire.md is the production path; this script
is throwaway scaffolding.

Usage:
    python scripts/adapt_v1_baton_to_v2.py \\
        --src-dir docs/ecp/2026-04-27-a231b248 \\
        --device mobile \\
        --out /tmp/phase-b-baton-mobile.json
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

IMPLICIT_ROLE = {
    "button": "button", "a": "link", "nav": "navigation", "header": "banner",
    "footer": "contentinfo", "main": "main", "h1": "heading", "h2": "heading",
    "h3": "heading", "img": "image", "form": "form",
}


def adapt(src_dir: Path, device: str) -> dict:
    baton_name = "baton.json" if device == "desktop" else "baton-mobile.json"
    v1 = json.loads((src_dir / baton_name).read_text(encoding="utf-8"))

    engagement_id = src_dir.name
    if not re.match(r"^\d{4}-\d{2}-\d{2}-[0-9a-f]{8}$", engagement_id):
        engagement_id = "2026-04-27-aaaaaaaa"

    viewport_w = (v1.get("viewport") or {}).get("width") or (390 if device == "mobile" else 1920)
    viewport_h = (v1.get("viewport") or {}).get("height") or (844 if device == "mobile" else 1080)
    dpr = (v1.get("viewport") or {}).get("dpr") or (3 if device == "mobile" else 1)

    v2 = {
        "schema_version": 1,
        "engagement_id": engagement_id,
        "device": device,
        "url": v1.get("url") or "https://www.slingmods.com",
        "captured_at": v1.get("captured_at") or "2026-04-27T16:14:02.000Z",
        "viewport": {
            "width": int(viewport_w),
            "height": int(viewport_h),
            "dpr_requested": float(dpr),
            "dpr_actual": 1.0 if v1.get("dpr_fallback") else float(dpr),
        },
        "capture_state": {
            "hydration": "pre-hydration" if v1.get("pre_hydration_warning") else "post-hydration",
            "overlays_detected": [],
            "page_height_px": int(v1.get("naturalHeight") or 5000),
        },
        "elements": [],
        "sections": [],
        "page_head": {
            "title": None,
            "canonical": None,
            "meta_description": None,
            "viewport_meta": None,
            "og_image": None,
            "schema_jsonld": v1.get("structured_data") or [],
            "hreflang": [],
        },
    }

    for i, el in enumerate(v1.get("elements", []) or []):
        tag = (el.get("tag") or "").lower() or "div"
        text = (el.get("text") or "")[:240]
        cls = (el.get("class") or "")[:240]
        v2["elements"].append({
            "e_index": f"e{i}",
            "tag": tag,
            "selector": (el.get("selector") or tag)[:512],
            "rect": {
                # Clamp to >=0: off-canvas elements yield negative
                # getBoundingClientRect coords, which schema/baton-v1.json
                # (rect.* minimum: 0) rejects.
                "x": max(0.0, float(el.get("x", 0))),
                "y": max(0.0, float(el.get("y", 0))),
                "width": max(0.0, float(el.get("width", 0))),
                "height": max(0.0, float(el.get("height", 0))),
            },
            "scroll_y_at_capture": 0,
            "role": IMPLICIT_ROLE.get(tag, tag or "group"),
            "accessible_name": (text or cls)[:240],
            "text_content": text,
            "is_above_fold": float(el.get("y", 0)) < float(viewport_h),
            "is_sticky": False,
            "is_offscreen": not bool(el.get("visible", True)),
        })

    # Pull sections from a relevant cluster-context (pricing if available)
    for cluster in ["pricing", "visual-cta", "trust-credibility"]:
        ctx_path = src_dir / f"cluster-context-{cluster}-{device}.json"
        if ctx_path.is_file():
            ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
            for s_idx, sec in enumerate(ctx.get("sections", []) or []):
                label = (sec.get("label") or f"Section {s_idx+1}")[:120]
                slug_raw = label.lower().replace(" ", "-").replace("_", "-")
                slug = re.sub(r"[^a-z0-9-]", "", slug_raw).strip("-")[:60]
                if not slug or not re.match(r"^[a-z]", slug):
                    slug = f"section-{s_idx+1}"
                section = {
                    "label": label,
                    "slug": slug,
                    "clusters": sec.get("clusters") or ["pricing"],
                    "scroll_y_top": int(sec.get("scrollY", 0)),
                    "scroll_y_bottom": int(sec.get("scrollY", 0)) + int(sec.get("height", 800)),
                    "screenshot_ref": f"section-{s_idx+1}-mobile.jpg" if device == "mobile" else f"section-{s_idx+1}.jpg",
                }
                v2["sections"].append(section)
            if v2["sections"]:
                break

    if not v2["sections"]:
        v2["sections"].append({
            "label": "Default section",
            "slug": "page",
            "clusters": ["pricing"],
            "scroll_y_top": 0,
            "scroll_y_bottom": 1000,
        })

    return v2


def main() -> int:
    parser = argparse.ArgumentParser(description="Adapt v1 baton to v2 shape (smoke test only).")
    parser.add_argument("--src-dir", type=Path, required=True)
    parser.add_argument("--device", choices=["desktop", "mobile"], required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    v2 = adapt(args.src_dir, args.device)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(v2, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.out}: {len(v2['elements'])} elements, {len(v2['sections'])} sections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
