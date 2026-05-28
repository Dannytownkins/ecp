#!/usr/bin/env python3
"""ECP Visual Report Generator — CLI entry point.

v1 path: ``generate_report`` reads v1 markdown audit + baton + sources;
fuzzy-matches CSS selectors against baton elements via the 5-tier resolver
in ``scripts/report/markers.py``. Triggered by default OR explicitly via
``--legacy-v1``.

v2 path: ``generate_v2_report`` reads cluster-emission-v1.json files +
synthesizer markdown + synthesizer-emission JSON; resolves hotspots via
direct e_index dictionary lookup against baton, with absent + section-
centroid + banner strategies for ``baton_index='absent'`` findings. Auto-
detected when ``synthesizer-emission-v1.json`` is present in the engagement
directory; can be forced with ``--v2`` or suppressed with ``--legacy-v1``.

v2 alt renderers (Phase G deliverable 5): ``--alt-format`` selects a non-
HTML output (markdown-mirror, bulleted, plain-prose). The HTML path is
the default.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from report.html_builder import generate_report
from report.v2_html_builder import generate_v2_report
from assembly.review_state import (
    generate_editor_artifacts,
    render_final_report,
    validate_review_state,
)


def _engagement_has_v2_inputs(engagement_dir: Path) -> bool:
    """Auto-detect v2 inputs by presence of synthesizer-emission-v1.json."""
    return (engagement_dir / "synthesizer-emission-v1.json").exists()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate E-Commerce Psychology visual report")
    parser.add_argument("--engagement", required=True, help="Path to engagement directory")
    parser.add_argument(
        "--device", required=True,
        choices=["mobile", "laptop", "desktop"],
        help="Device name",
    )
    parser.add_argument(
        "--audit", default=None,
        help="Audit filename. v1 default: audit.md / audit-{device}.md. v2 default: audit-{device}.md.",
    )
    parser.add_argument(
        "--baton", default=None,
        help="Baton filename. Defaults to baton.json (desktop/laptop) or baton-{device}.json.",
    )
    parser.add_argument("--plugin-root", required=True, help="Path to plugin root directory")
    parser.add_argument("--markers", default=None, help="Path to marker overrides JSON (v2 merges; v1 replaces)")
    parser.add_argument("--output", default=None, help="Output filename (auto-generated if omitted)")
    parser.add_argument(
        "--from-review",
        default=None,
        help="Render final HTML from a review-state JSON file instead of generating an AI draft report.",
    )
    parser.add_argument(
        "--validate-review-state",
        default=None,
        help="Validate a review-state JSON file and print schema/business reference errors without rendering.",
    )
    parser.add_argument(
        "--list-imports",
        default=None,
        help="List imported assets referenced by a review-state JSON file.",
    )
    parser.add_argument(
        "--mark-client-verified",
        action="store_true",
        help=(
            "Promote the engagement's report from DRAFT to CLIENT-VERIFIED "
            "(product.md §6 manual verification pass). Operator action only — "
            "refuses to run under --auto."
        ),
    )
    parser.add_argument(
        "--mark-reflection-complete",
        action="store_true",
        help=(
            "Attest that lead-reflection.md matches the pipeline's actual "
            "end-state — flips reflection_state from DRAFT to COMPLETE in "
            "meta.json (G23). The lead invokes this at audit completion "
            "after canaries pass and the reflection narrative has been "
            "written/verified against on-disk artifacts. Refuses to run "
            "under --auto: premature finalization is the failure mode "
            "this guard exists to prevent."
        ),
    )
    parser.add_argument(
        "--skip-editor",
        action="store_true",
        help="With --v2, skip editor.html and review-state generation.",
    )
    parser.add_argument(
        "--overwrite-review-state",
        action="store_true",
        help="With --v2, replace existing review-state files. Use carefully; this can replace human edits.",
    )
    parser.add_argument(
        "--v2", action="store_true",
        help="Force v2 renderer (auto-detected when synthesizer-emission-v1.json present).",
    )
    parser.add_argument(
        "--legacy-v1", action="store_true",
        help="Force v1 renderer even when v2 inputs are present.",
    )
    parser.add_argument(
        "--auto", action="store_true",
        help=(
            "Signal automated/unattended execution. A report can never be "
            "promoted to client-verified under --auto (product.md §6)."
        ),
    )
    parser.add_argument(
        "--alt-format",
        choices=["html", "markdown-mirror", "bulleted", "plain-prose"],
        default="html",
        help="v2 alt renderer (Phase G deliverable 5). Default: html.",
    )

    args = parser.parse_args()

    engagement_path = Path(args.engagement)

    if args.mark_client_verified:
        from assembly.report_state import AutoPromotionError, set_client_verified

        meta_path = engagement_path / "meta.json"
        if not meta_path.exists():
            print(f"meta.json not found: {meta_path}", file=sys.stderr)
            return 1
        try:
            set_client_verified(meta_path, auto=args.auto)
        except AutoPromotionError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(f"report_state set to client-verified: {meta_path}")
        return 0

    if args.mark_reflection_complete:
        from assembly.reflection_state import (
            AutoCompletionError, set_reflection_complete,
        )

        meta_path = engagement_path / "meta.json"
        if not meta_path.exists():
            print(f"meta.json not found: {meta_path}", file=sys.stderr)
            return 1
        try:
            set_reflection_complete(meta_path, auto=args.auto)
        except AutoCompletionError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(f"reflection_state set to complete: {meta_path}")
        return 0

    if args.validate_review_state:
        import json

        review_path = Path(args.validate_review_state)
        if not review_path.is_absolute():
            review_path = engagement_path / review_path
        state = json.loads(review_path.read_text(encoding="utf-8"))
        errors = validate_review_state(state)
        if errors:
            print(f"review state invalid: {review_path}", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            return 1
        print(f"review state valid: {review_path}")
        return 0

    if args.list_imports:
        import json

        review_path = Path(args.list_imports)
        if not review_path.is_absolute():
            review_path = engagement_path / review_path
        state = json.loads(review_path.read_text(encoding="utf-8"))
        imports = state.get("imported_assets") or []
        if not imports:
            print("No imported assets.")
            return 0
        for asset in imports:
            source = asset.get("source") or "(embedded data_url only)"
            size = ""
            if asset.get("source"):
                candidate = (engagement_path / asset["source"]).resolve()
                try:
                    if candidate.is_relative_to(engagement_path.resolve()) and candidate.exists():
                        size = f" {candidate.stat().st_size} bytes"
                except OSError:
                    pass
            print(f"{asset.get('name', '(unnamed)')} -> {source}{size}")
        return 0

    if args.from_review:
        review_path = Path(args.from_review)
        if not review_path.is_absolute():
            review_path = (engagement_path / review_path).resolve()
        else:
            review_path = review_path.resolve()
        import json

        state = json.loads(review_path.read_text(encoding="utf-8"))
        device = state.get("device") or args.device
        output_name = args.output or f"visual-report-{device}-final.html"
        if _engagement_has_v2_inputs(engagement_path) and not args.legacy_v1:
            output_path = generate_v2_report(
                engagement_dir=str(engagement_path),
                device=device,
                plugin_root=args.plugin_root,
                audit_file=args.audit,
                baton_file=args.baton,
                markers_file=args.markers,
                output_file=output_name,
                review_state_file=review_path,
            )
            print(f"final report written to: {output_path}")
            return 0

        audit_file = args.audit
        if audit_file is None:
            device_audit = f"audit-{device}.md"
            audit_file = device_audit if (engagement_path / device_audit).exists() else (
                "audit.md" if device in ("desktop", "laptop") else f"audit-{device}.md"
            )
        baton_file = args.baton or ("baton.json" if device in ("desktop", "laptop") else f"baton-{device}.json")
        if (engagement_path / audit_file).exists() and (engagement_path / baton_file).exists():
            generate_report(
                engagement_dir=str(engagement_path),
                device=device,
                audit_file=audit_file,
                baton_file=baton_file,
                plugin_root=args.plugin_root,
                markers_file=args.markers,
                output_file=output_name,
                review_state_file=review_path,
            )
            return 0

        html = render_final_report(state, engagement_path, device=device)
        output_path = engagement_path / output_name
        output_path.write_text(html, encoding="utf-8")
        print(f"final report written to: {output_path}")
        return 0

    use_v2 = args.v2 or (_engagement_has_v2_inputs(engagement_path) and not args.legacy_v1)

    if args.alt_format != "html" and not use_v2:
        print(
            f"ERROR: --alt-format {args.alt_format} requires v2 inputs (synthesizer-emission-v1.json). "
            f"Engagement directory has no v2 inputs.",
            file=sys.stderr,
        )
        return 2

    if args.alt_format != "html":
        # v2 alt renderers (markdown-mirror, bulleted, plain-prose)
        from report.v2_renderers import generate_v2_alt_render
        out = generate_v2_alt_render(
            engagement_dir=engagement_path,
            device=args.device,
            audit_file=args.audit,
            baton_file=args.baton,
            output_file=args.output,
            alt_format=args.alt_format,
            plugin_root=Path(args.plugin_root),
        )
        print(f"v2 {args.alt_format} written to: {out}")
        return 0

    if use_v2:
        out = generate_v2_report(
            engagement_dir=str(engagement_path),
            device=args.device,
            plugin_root=args.plugin_root,
            audit_file=args.audit,
            baton_file=args.baton,
            markers_file=args.markers,
            output_file=args.output,
        )
        if not args.skip_editor:
            outputs = generate_editor_artifacts(
                engagement_path,
                Path(args.plugin_root),
                overwrite_review_state=args.overwrite_review_state,
            )
            if outputs:
                print("editor artifacts written:")
                for label, path in outputs.items():
                    print(f"  {label}: {path}")
        return 0

    # v1 path
    audit_file = args.audit or ("audit.md" if args.device in ("desktop", "laptop") else f"audit-{args.device}.md")
    baton_file = args.baton or ("baton.json" if args.device in ("desktop", "laptop") else f"baton-{args.device}.json")
    generate_report(
        engagement_dir=str(engagement_path),
        device=args.device,
        audit_file=audit_file,
        baton_file=baton_file,
        plugin_root=args.plugin_root,
        markers_file=args.markers,
        output_file=args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
