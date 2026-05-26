"""CLI entry point for the ECP Audit Assembly pipeline.

Usage:
    python assemble-audit.py --engagement <path> --device <mobile|laptop|desktop> [options]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from assembly.parser import load_all_cluster_files
from assembly.dedup import deduplicate
from assembly.scoring import score_groups
from assembly.writer import write_audit_md, write_sidecars
from assembly.pipeline import FinalizedFindings
from assembly.synthesizer_parser import parse_response, validate_stories
from assembly.meta_validator import validate_meta_json
from report.path_safety import resolve_within_base

DEVICE_LABELS = {
    "mobile": "Mobile (390x844 @ 3x DPR)",
    "laptop": "Laptop (1440x900 @ 1x DPR)",
    "desktop": "Desktop (1920x1080 @ 1x DPR)",
}


def _output_filename(device: str, devices_requested: list[str]) -> str:
    """Determine the output filename for a given device.

    Rules:
    - laptop always gets "audit.md" (bare)
    - first device in devices_requested gets "audit.md" (bare)
    - second and beyond get "audit-{device}.md"
    """
    if device == "laptop":
        return "audit.md"
    if not devices_requested or device == devices_requested[0]:
        return "audit.md"
    return f"audit-{device}.md"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assemble ECP audit findings from cluster files into audit.md",
    )
    parser.add_argument(
        "--engagement",
        required=True,
        help="Path to the engagement directory (containing meta.json and cluster files)",
    )
    parser.add_argument(
        "--device",
        required=True,
        choices=["mobile", "laptop", "desktop"],
        help="Which device's cluster files to assemble",
    )
    parser.add_argument(
        "--no-sidecar",
        action="store_true",
        help="Skip writing sidecar JSON files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print a summary without writing any files",
    )
    parser.add_argument(
        "--priority-path",
        dest="priority_path",
        default=None,
        metavar="PATH",
        help=(
            "Path to a text file containing the synthesizer subagent's "
            "response (one fenced JSON code block with a 'stories' array). "
            "When provided, the Priority Path section is rendered from "
            "the synthesized stories instead of the empty-state "
            "placeholder. The file is parsed + validated with "
            "scripts/assembly/synthesizer_parser.py; a hallucinated F-N "
            "or malformed JSON causes a visible ERROR block to render "
            "instead of silent placeholder."
        ),
    )
    parser.add_argument(
        "--skip-lint",
        action="store_true",
        help=(
            "Skip the pre-assembly cluster-file lint pass. Default is to run "
            "scripts/validate-cluster-files.py first; any violations print "
            "as warnings but DO NOT block assembly (the assembler already "
            "parses what it can). Pass --skip-lint to suppress the lint "
            "entirely — useful when iterating on the linter itself."
        ),
    )

    args = parser.parse_args()

    # -----------------------------------------------------------------------
    # 1. Validate engagement directory and load meta.json
    # -----------------------------------------------------------------------
    engagement_dir = Path(args.engagement).resolve()
    if not engagement_dir.is_dir():
        print(f"Error: engagement directory not found: {engagement_dir}", file=sys.stderr)
        sys.exit(1)

    meta_path = engagement_dir / "meta.json"
    if not meta_path.exists():
        print(f"Error: meta.json not found in {engagement_dir}", file=sys.stderr)
        sys.exit(1)

    # M2 — surface duplicate-key corruption and invariant violations in
    # meta.json. Warnings print to stderr; we don't abort the run because
    # (a) the legacy engagements on disk predate this validator, and
    # (b) the bug is upstream (lead agent overwrites instead of merging).
    # The validator is the downstream safety net that makes the corruption
    # visible to the operator.
    meta_warnings = validate_meta_json(meta_path)
    for warning in meta_warnings:
        print(f"meta.json warning: {warning}", file=sys.stderr)

    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    # -----------------------------------------------------------------------
    # 2. Get clusters from meta
    # -----------------------------------------------------------------------
    clusters: list[str] = meta.get("clusters_used", [])
    if not clusters:
        print("Error: meta.json has no clusters_used", file=sys.stderr)
        sys.exit(1)

    device = args.device
    device_label = DEVICE_LABELS.get(device, device)

    # -----------------------------------------------------------------------
    # 2b. Pre-assembly lint (format + self-cite + ethics URL + DPR units)
    # -----------------------------------------------------------------------
    # Surface the failure patterns from the 2026-04-21 engagement BEFORE
    # we parse and silently drop findings. Warnings do NOT block assembly
    # (the assembler still extracts whatever it can) but they give the
    # lead a clear signal to re-dispatch the offending auditor teammate
    # via SendMessage. See scripts/validate-cluster-files.py.
    if not args.skip_lint:
        import subprocess
        lint_script = Path(__file__).resolve().parent / "validate-cluster-files.py"
        if lint_script.exists():
            lint_result = subprocess.run(
                [sys.executable, str(lint_script), "--engagement", str(engagement_dir), "--warn-only"],
                capture_output=True,
                text=True,
            )
            # Only print lint output when something failed; OK runs are
            # silent so the assembly summary stays clean.
            if "FAIL" in lint_result.stdout:
                print("Pre-assembly lint found issues:", file=sys.stderr)
                print(lint_result.stdout, file=sys.stderr)
                if lint_result.stderr.strip():
                    print(lint_result.stderr, file=sys.stderr)

    # -----------------------------------------------------------------------
    # 3. Parse cluster files
    # -----------------------------------------------------------------------
    print(f"Assembling {device_label} audit from {len(clusters)} clusters...")

    try:
        findings, pass_findings, ethics = load_all_cluster_files(engagement_dir, device, clusters)
    except FileNotFoundError as exc:
        # load_all_cluster_files raises when any cluster in clusters_used has
        # no corresponding cluster-{slug}-{device}.md file. Print the error
        # message (which includes the actionable resolution path) and exit
        # with code 3 to distinguish from the exit-2 path-containment failures
        # and exit-1 generic missing-input failures.
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(3)

    if not findings:
        # Zero FAIL/PARTIAL findings is NOT fatal. A legitimate clean audit
        # (well-built page, everything passing) should produce a valid empty
        # report with 0/0/0/0 severity counts and a placeholder Priority
        # Path, NOT crash with sys.exit(1). Codex Phase 2 flagged the old
        # behavior — customers with a genuinely-clean page hit a CLI error
        # and think the pipeline is broken.
        #
        # The rest of the pipeline handles empty findings gracefully:
        # dedup produces an empty DedupeResult, FinalizedFindings has an
        # empty cluster_finding_map, the writer renders a valid empty
        # audit.md, and write_sidecars emits [] for each JSON file.
        print(
            f"Notice: no FAIL/PARTIAL findings parsed for device={device}. "
            "Proceeding with empty audit - this is the correct artifact "
            "for a genuinely clean page or an over-strict min-priority filter.",
            file=sys.stderr,
        )

    # Zero-count warning per cluster — a cluster file that parses to 0 findings
    # is almost always a format-drift failure (auditor wrote Markdown headings
    # or bold-prose fields instead of triple-backtick FINDING code blocks),
    # not a genuinely empty cluster. Documented in 2026-04-14 postmortem #3.
    from collections import Counter as _Counter
    per_cluster = _Counter(f.cluster for f in findings)
    zero_clusters = [c for c in clusters if per_cluster.get(c, 0) == 0]
    if zero_clusters:
        cluster_file = lambda c: engagement_dir / f"cluster-{c}-{device}.md"
        print(
            "WARNING: {n} cluster file(s) parsed to 0 findings - this usually means "
            "the auditor used a non-canonical format (Markdown heading style or "
            "bold-prose fields) instead of triple-backtick FINDING code blocks. "
            "Check workflows/audit.md Step 4a. Affected:".format(n=len(zero_clusters)),
            file=sys.stderr,
        )
        for c in zero_clusters:
            exists = cluster_file(c).exists()
            tag = "file missing" if not exists else "0 findings parsed"
            print(f"  - {c}-{device}: {tag} ({cluster_file(c).name})", file=sys.stderr)

    print(f"Parsed {len(findings)} raw findings.")

    # -----------------------------------------------------------------------
    # 7. Deduplicate
    # -----------------------------------------------------------------------
    result = deduplicate(findings, pass_findings)

    auto_merged_count = len(result.auto_merged)
    fuzzy_count = len(result.fuzzy_candidates)
    input_count = len(findings)
    output_count = len(result.kept) + len(result.ethics_findings)

    print(
        f"Dedup: {input_count} in -> {output_count} out "
        f"({auto_merged_count} auto-merged, {fuzzy_count} fuzzy candidates)"
    )

    # -----------------------------------------------------------------------
    # 9. Dry run: print summary and exit
    # -----------------------------------------------------------------------
    if args.dry_run:
        from collections import Counter
        priority_counts: Counter[str] = Counter()
        for f in result.kept + result.ethics_findings:
            priority_counts[f.priority] += 1

        print()
        print("=== DRY RUN SUMMARY ===")
        print(f"  Device:          {device_label}")
        print(f"  Engagement:      {meta.get('engagement_id', 'unknown')}")
        print(f"  Clusters:        {', '.join(clusters)}")
        print(f"  Ethics status:   {ethics}")
        print(f"  Raw findings:    {input_count}")
        print(f"  After dedup:     {output_count}")
        print(f"    CRITICAL:      {priority_counts.get('CRITICAL', 0)}")
        print(f"    HIGH:          {priority_counts.get('HIGH', 0)}")
        print(f"    MEDIUM:        {priority_counts.get('MEDIUM', 0)}")
        print(f"    LOW:           {priority_counts.get('LOW', 0)}")
        print(f"  Auto-merged:     {auto_merged_count}")
        print(f"  Fuzzy groups:    {fuzzy_count}")
        print(f"  Passes (deduped): {len(result.pass_findings)}")
        print(f"  Synthesis groups: {len(result.synthesis_groups)}")
        print()
        print("No files written (--dry-run).")
        return

    # -----------------------------------------------------------------------
    # 10. Build FinalizedFindings (post-dedup, display-index-assigned).
    #     `FinalizedFindings.build` runs assign_display_indices, wraps the
    #     result in an immutable frozen dataclass, and exposes valid_refs()
    #     for synthesizer validation. Replaces the earlier split between a
    #     bare assign_display_indices call + an inline set-comprehension
    #     for valid_refs. Single abstraction wins both places.
    # -----------------------------------------------------------------------
    finalized = FinalizedFindings.build(
        list(result.ethics_findings) + list(result.kept),
        clusters,
    )

    # -----------------------------------------------------------------------
    # 11. Score Priority Path candidates (now emits display_index-based refs)
    # -----------------------------------------------------------------------
    candidates = score_groups(result.synthesis_groups, result.kept)

    # -----------------------------------------------------------------------
    # 11b. Load + validate synthesizer response (if --priority-path given)
    # -----------------------------------------------------------------------
    priority_path_stories = None
    if args.priority_path:
        # Path containment: require the synth response file to live inside
        # the engagement directory. Its contents are parsed into Priority
        # Path stories and embedded into audit.md; a crafted --priority-path
        # pointing at an arbitrary file could smuggle content through the
        # validator boundary (malformed JSON would be caught, but large
        # truthy JSON payloads embedded as narrative_md/action_md would
        # not be). Containment is the cheap guard.
        try:
            synth_path = resolve_within_base(args.priority_path, engagement_dir)
        except ValueError as exc:
            print(
                f"Error: --priority-path rejected (must live inside engagement dir): {exc}",
                file=sys.stderr,
            )
            sys.exit(2)
        if not synth_path.exists():
            print(
                f"Error: --priority-path {synth_path} does not exist",
                file=sys.stderr,
            )
            sys.exit(1)
        synth_text = synth_path.read_text(encoding="utf-8")
        parsed = parse_response(synth_text)
        if parsed is None:
            print(
                f"Warning: --priority-path {synth_path} did not yield parseable "
                "stories (missing fenced JSON block or malformed JSON). "
                "Rendering ERROR block in audit.md.",
                file=sys.stderr,
            )
            priority_path_stories = []  # triggers ERROR render in writer
        else:
            # Allowlist comes straight from FinalizedFindings so the synthesizer
            # is validated against the exact same frozen set the writer sees.
            valid_refs = finalized.valid_refs()
            ok, reason = validate_stories(parsed, valid_refs)
            if not ok:
                print(
                    f"Warning: --priority-path {synth_path} failed validation: "
                    f"{reason}. Rendering ERROR block in audit.md.",
                    file=sys.stderr,
                )
                priority_path_stories = []  # triggers ERROR render
            else:
                priority_path_stories = parsed

    # -----------------------------------------------------------------------
    # 11. Determine output filename
    # -----------------------------------------------------------------------
    devices_requested: list[str] = meta.get("devices_requested", [])
    filename = _output_filename(device, devices_requested)
    output_path = engagement_dir / filename

    # -----------------------------------------------------------------------
    # 12. Write audit.md
    # -----------------------------------------------------------------------
    total, finding_groups = write_audit_md(
        output_path=output_path,
        result=result,
        meta=meta,
        device=device,
        device_label=device_label,
        ethics_status=ethics,
        priority_path_stories=priority_path_stories,
    )

    print(f"Wrote {filename}: {total} findings")

    # -----------------------------------------------------------------------
    # 14. Write sidecar JSON files
    # -----------------------------------------------------------------------
    if not args.no_sidecar:
        write_sidecars(
            engagement_dir=engagement_dir,
            result=result,
            candidates=candidates,
            finding_groups=finding_groups,
            device=device,
            # H1: pass validated stories so the renderer can read them from
            # a JSON sidecar instead of re-parsing the audit.md markdown.
            # Prevents stale/hand-edited audit.md from smuggling bogus F-N
            # refs past the synthesizer validator.
            priority_path_stories=priority_path_stories,
        )

    # -----------------------------------------------------------------------
    # 15. Done
    # -----------------------------------------------------------------------
    if args.priority_path:
        print(f"Done. {filename} assembled with Priority Path stories.")
    else:
        # Loud warning — empty Priority Path is a silent failure mode that
        # only surfaces when an operator opens the visual report and sees
        # "No priority path stories for this audit." Make it noisy at
        # assembly time so the lead remembers to dispatch the synthesizer
        # subagent (see contracts/priority-path-synthesis.md).
        print(
            f"Done. {filename} written WITHOUT Priority Path "
            f"(empty-state placeholder rendered).",
            file=sys.stderr,
        )
        print(
            f"NEXT STEP: dispatch the Priority Path synthesizer subagent "
            f"per contracts/priority-path-synthesis.md, capture its "
            f"response to a .txt file, then re-run this script with "
            f"--priority-path <file>. Skipping this step ships an audit "
            f"with no prioritized action stories.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
