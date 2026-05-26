"""audit.md writer and sidecar output for the ECP Audit Assembly package."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

from .models import DedupeResult, Finding

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

VIEWPORT_STRINGS = {
    "mobile": "390x844 @ 3x DPR",
    "laptop": "1440x900 @ 1x DPR",
    "desktop": "1920x1080 @ 1x DPR",
}

# Sidecar filename suffix: laptop uses no device suffix, others use -{device}
def _sidecar_suffix(device: str) -> str:
    return "" if device == "laptop" else f"-{device}"


# ---------------------------------------------------------------------------
# Block reconstruction
# ---------------------------------------------------------------------------


def _reconstruct_block(finding: Finding) -> str:
    """Build a code-fenced finding block from parsed fields.

    Used when raw_block is empty. Field order matches the original format.
    """
    lines = ["FINDING: " + finding.verdict]

    if finding.title:
        lines.append(f"TITLE: {finding.title}")
    if finding.section:
        lines.append(f"SECTION: {finding.section}")
    if finding.element:
        lines.append(f"ELEMENT: {finding.element}")
    if finding.synthesis_hint:
        lines.append(f"SYNTHESIS_HINT: {finding.synthesis_hint}")
    if finding.source:
        lines.append(f"SOURCE: {finding.source}")
    if finding.observation:
        lines.append(f"OBSERVATION: {finding.observation}")
    if finding.recommendation:
        lines.append(f"RECOMMENDATION: {finding.recommendation}")
    if finding.reference:
        lines.append(f"REFERENCE: {finding.reference}")
    if finding.priority:
        lines.append(f"PRIORITY: {finding.priority}")
    if finding.ethics_state:
        lines.append(f"ETHICS_STATE: {finding.ethics_state}")
    if finding.source_url:
        lines.append(f"SOURCE_URL: {finding.source_url}")
    if finding.why_matters:
        lines.append(f"**Why this matters:** {finding.why_matters}")
    if finding.citation:
        tier_suffix = f" [{finding.tier}]" if finding.tier else ""
        lines.append(f"↳ {finding.citation}{tier_suffix}")

    return "\n".join(lines)


def _render_finding_block(finding: Finding) -> str:
    """Return the full code-fenced string for a finding.

    Uses raw_block verbatim when available; falls back to reconstruction.
    If the finding has merged_from refs, appends them before the closing fence.
    """
    if finding.raw_block:
        inner = finding.raw_block
    else:
        inner = _reconstruct_block(finding)

    if finding.merged_from:
        refs = ", ".join(finding.merged_from)
        inner = inner.rstrip() + f"\nAlso identified by: {refs}"

    return f"```\n{inner}\n```"


# ---------------------------------------------------------------------------
# Ethics gate summary
# ---------------------------------------------------------------------------


def _ethics_gate_header(ethics_findings: List[Finding]) -> str:
    """Derive the ethics gate header from the structured findings list.

    Single source of truth: header and summary both read from the same list,
    so they cannot disagree. Fixes the C3 split-brain where the header could
    say VIOLATIONS FOUND while the summary said 0 BLOCK findings detected.
    """
    if any(f.ethics_state == "BLOCK" for f in ethics_findings):
        return "VIOLATIONS FOUND"
    if any(f.ethics_state == "ADJACENT" for f in ethics_findings):
        return "ADVISORY"
    return "CLEAR"


def _ethics_gate_summary(ethics_findings: List[Finding]) -> str:
    """Build the ethics gate body text from the same findings the header reads."""
    blocks = [f for f in ethics_findings if f.ethics_state == "BLOCK"]
    adjacent = [f for f in ethics_findings if f.ethics_state == "ADJACENT"]
    if blocks:
        count = len(blocks)
        word = "finding" if count == 1 else "findings"
        return (
            f"{count} BLOCK ethics {word} detected. "
            "These require immediate review before this audit is delivered to the client. "
            "See BLOCK findings at the top of the Findings section."
        )
    if adjacent:
        count = len(adjacent)
        word = "finding" if count == 1 else "findings"
        return (
            f"{count} ADJACENT ethics {word} flagged. "
            "No hard violations detected; review flagged items before delivery."
        )
    return "No BLOCK or ADJACENT ethics findings detected."


# ---------------------------------------------------------------------------
# Synthesis hint section
# ---------------------------------------------------------------------------


def _render_synthesis_section(synthesis_groups: Dict[str, List[Finding]]) -> str:
    """Build the Cross-Cluster Connections section body.

    F-N references use ``display_index`` (post-dedup, cluster-local,
    1-based) so they match the F-N labels the renderer uses for finding
    cards. Pre-M1 the section used ``local_index`` (pre-dedup, from
    the raw cluster file), which drifted from the rendered finding
    numbers in the same way the Priority Path used to drift (Codex
    Phase 1 MEDIUM, same bug class as the Priority Path F-N drift
    Track A Fix 1 addressed).

    ``display_index`` is assigned by ``pipeline.assign_display_indices``
    before write_audit_md runs — it's guaranteed non-zero for every
    finding that reaches this function.
    """
    if not synthesis_groups:
        return "_No cross-cluster connections identified._"

    lines: List[str] = []
    for slug, findings in synthesis_groups.items():
        # display_index, not local_index — matches renderer F-N labels.
        refs = ", ".join(
            f"{f.cluster} F-{(f.display_index or f.local_index):02d}"
            for f in findings
        )
        title = slug.replace("-", " ").replace("_", " ").title()
        clusters = sorted({f.cluster for f in findings})
        cluster_str = ", ".join(clusters)
        lines.append(f"**{title}** ({cluster_str}): {refs}")

    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Public: write_audit_md
# ---------------------------------------------------------------------------


def write_audit_md(
    output_path: Path,
    result: DedupeResult,
    meta: dict,
    device: str,
    device_label: str,
    ethics_status: str,
    priority_path_stories: "List[dict] | None" = None,
) -> Tuple[int, List[dict]]:
    """Write the consolidated audit.md file.

    Args:
        priority_path_stories: optional list of Story dicts from the
            synthesizer subagent (see
            ``scripts/assembly/synthesizer_parser.py``). When supplied,
            the Priority Path section renders real stories with F-N
            anchors back to finding cards. Any ``f_refs`` that don't
            resolve to a real finding in the rendered order trigger a
            visible ERROR render rather than a broken anchor. When
            ``None``, the section renders a placeholder pointing the
            lead at the synthesizer dispatch step.

    Returns:
        (total_finding_count, finding_groups)

    finding_groups is a list of dicts, one per (cluster, section) pair:
        {
            "cluster": str,
            "section": str,
            "highest_severity": str,
            "count": int,
            "finding_indices": [int, ...],  # display_index values
        }
    """
    from .pipeline import assign_display_indices, _assert_stage
    _assert_stage("write_audit", 4)

    engagement_id = meta.get("engagement_id") or meta.get("id", "unknown")
    url = meta.get("url") or (meta.get("page") or {}).get("url", "")
    platform = meta.get("platform", "")
    date = (meta.get("created") or "")[:10]  # ISO date prefix
    clusters_used: List[str] = meta.get("clusters_used", [])
    clusters_str = ", ".join(clusters_used)

    viewport_str = VIEWPORT_STRINGS.get(device, device)

    # Combine ethics BLOCK findings + kept findings. assign_display_indices
    # sorts cluster-by-cluster in the same order the renderer uses below
    # AND tags every finding with its final display_index (the F-N it
    # will be rendered as). After this call, scoring._finding_ref emits
    # references that match the displayed position. If the orchestrator
    # already called assign_display_indices before scoring, this second
    # call is idempotent (re-tags the same indices).
    all_findings: List[Finding] = assign_display_indices(
        list(result.ethics_findings) + list(result.kept),
        clusters_used,
    )

    # -----------------------------------------------------------------------
    # Group findings by cluster (preserving clusters_used order)
    # -----------------------------------------------------------------------
    by_cluster: Dict[str, List[Finding]] = defaultdict(list)
    for f in all_findings:
        by_cluster[f.cluster].append(f)

    # Preserve order from clusters_used; append any orphan clusters at the end
    ordered_clusters = [c for c in clusters_used if c in by_cluster]
    for c in by_cluster:
        if c not in ordered_clusters:
            ordered_clusters.append(c)

    # -----------------------------------------------------------------------
    # Build finding_groups metadata
    # -----------------------------------------------------------------------
    finding_groups: List[dict] = []

    for cluster in ordered_clusters:
        cluster_findings = by_cluster[cluster]
        # Group by section within the cluster
        by_section: Dict[str, List[Finding]] = defaultdict(list)
        for f in cluster_findings:
            by_section[f.section].append(f)

        for section, sec_findings in by_section.items():
            highest = min(sec_findings, key=lambda f: f.priority_rank).priority
            finding_groups.append({
                "cluster": cluster,
                "section": section,
                "highest_severity": highest,
                "count": len(sec_findings),
                "finding_indices": [f.display_index for f in sec_findings],
            })

    # -----------------------------------------------------------------------
    # Summary counts (from actual findings written)
    # -----------------------------------------------------------------------
    counts: Dict[str, int] = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in all_findings:
        p = f.priority.upper()
        if p in counts:
            counts[p] += 1
    total = sum(counts.values())

    # -----------------------------------------------------------------------
    # Build the markdown document
    # -----------------------------------------------------------------------
    parts: List[str] = []

    # Header
    parts.append(f"# E-Commerce Psychology Audit: {engagement_id} ({device_label})")
    parts.append("")
    parts.append(f"**URL:** {url}")
    parts.append(f"**Viewport:** {device} {viewport_str}")
    parts.append(f"**Platform:** {platform}")
    parts.append(f"**Date:** {date}")
    parts.append(f"**Engagement:** {engagement_id}")
    parts.append(f"**Clusters audited:** {clusters_str}")
    parts.append("")
    parts.append("---")
    parts.append("")

    # Ethics Gate — header and summary both derive from result.ethics_findings
    # (no independent ethics_status that can disagree with the count; fixes C3).
    gate_header = _ethics_gate_header(result.ethics_findings)
    parts.append(f"## Ethics Gate: {gate_header}")
    parts.append("")
    parts.append(_ethics_gate_summary(result.ethics_findings))
    parts.append("")
    parts.append("---")
    parts.append("")

    # Priority Path — either real synthesized stories, or an ERROR/placeholder
    parts.append("## Priority Path")
    parts.append("")
    # Build the valid-refs set from the finalized display order so we can
    # verify every story's f_refs resolves to a real finding card.
    valid_refs = {
        f"{f.cluster} F-{f.display_index:02d}"
        for f in all_findings
    }
    parts.extend(_render_priority_path(priority_path_stories, valid_refs))
    parts.append("")
    parts.append("---")
    parts.append("")

    # Findings — findings come pre-sorted by assign_display_indices; do NOT
    # re-sort here (that caused the C2 F-N drift: scoring emitted refs from
    # pre-dedup order, writer re-sorted, and Priority Path links landed on
    # the wrong cards).
    parts.append("## Findings")
    parts.append("")

    for cluster in ordered_clusters:
        cluster_findings = by_cluster[cluster]

        parts.append(f"### {cluster} cluster")
        parts.append("")

        for f in cluster_findings:
            parts.append(_render_finding_block(f))
            parts.append("")

        parts.append("---")
        parts.append("")

    # Cross-Cluster Connections
    parts.append("## Cross-Cluster Connections")
    parts.append("")
    parts.append(_render_synthesis_section(result.synthesis_groups))
    parts.append("")
    parts.append("---")
    parts.append("")

    # What's Working Well
    parts.append("## What's Working Well")
    parts.append("")
    if result.pass_findings:
        seen: set[str] = set()
        for pf in result.pass_findings:
            key = pf.text.lower()[:80]
            if key not in seen:
                seen.add(key)
                parts.append(f"- {pf.text}")
    else:
        parts.append("_No passing items recorded._")
    parts.append("")
    parts.append("---")
    parts.append("")

    # Summary table
    parts.append("## Summary")
    parts.append("")
    parts.append("| Priority | Count |")
    parts.append("|----------|-------|")
    parts.append(f"| CRITICAL | {counts['CRITICAL']} |")
    parts.append(f"| HIGH | {counts['HIGH']} |")
    parts.append(f"| MEDIUM | {counts['MEDIUM']} |")
    parts.append(f"| LOW | {counts['LOW']} |")
    parts.append(f"| **Total** | **{total}** |")
    parts.append("")

    # Atomic write: materialise to audit.md.tmp in the same directory,
    # fsync, then os.replace. os.replace is atomic on both POSIX and
    # Windows when source and destination are on the same volume. Same
    # directory guarantees that in the happy case. Symlinks resolve
    # through; Windows junctions to a different volume are the only
    # real-world corner — detect and fall back to shutil.move.
    content = "\n".join(parts)
    _atomic_write(output_path, content)

    return total, finding_groups


def _render_priority_path(
    stories: "List[dict] | None",
    valid_refs: set,
) -> List[str]:
    """Return the markdown lines for the Priority Path section.

    - stories is None or []: render the synthesis placeholder.
    - any story.f_refs contains an F-N not in valid_refs: render an
      ERROR block instead of the stories. Broken anchors never ship.
    """
    if not stories:
        return [
            "<!-- Priority Path synthesis not yet run for this engagement."
            " Dispatch the synthesizer subagent per"
            " contracts/synthesizer-subagent.md,"
            " then re-run assemble-audit.py with --priority-path PATH. -->",
        ]

    # Validate every f_ref
    bad: List[Tuple[int, str]] = []  # (story_index, ref)
    for i, story in enumerate(stories, start=1):
        for ref in story.get("f_refs", []) or []:
            if ref not in valid_refs:
                bad.append((i, ref))
    if bad:
        lines = [
            "> **ERROR: Priority Path synthesis produced unresolvable F-N references.**",
            "> The synthesizer subagent cited finding IDs that do not appear in the",
            "> finalized audit. This block is rendered instead of story cards to",
            "> prevent broken anchors in the report. Re-run the synthesizer and",
            "> pass the corrected output to `--priority-path`.",
            ">",
        ]
        for story_idx, ref in bad:
            lines.append(f"> - story #{story_idx}: `{ref}` — not in the displayed finding set")
        return lines

    # Render stories
    lines: List[str] = []
    for i, story in enumerate(stories, start=1):
        title = story.get("title", "(untitled)")
        severity = story.get("severity", "MEDIUM").upper()
        lines.append(f"### {i}. {title} ({severity})")
        lines.append("")
        narrative = (story.get("narrative_md") or "").strip()
        if narrative:
            lines.append(narrative)
            lines.append("")
        action = (story.get("action_md") or "").strip()
        if action:
            lines.append(f"**Do this:** {action}")
            lines.append("")
        refs = story.get("f_refs") or []
        if refs:
            lines.append("**Underlying findings:** " + ", ".join(f"`{r}`" for r in refs))
            lines.append("")
    return lines


def _atomic_write(target: Path, content: str) -> None:
    """Write ``content`` to ``target`` atomically.

    Writes to ``target.with_suffix(target.suffix + '.tmp')`` in the same
    directory, fsyncs, then os.replace. When target and tmp land on
    different volumes (Windows junction pointing out, unusual mount),
    fall back to ``shutil.move`` with a warning.
    """
    import os
    import shutil
    import sys

    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    try:
        with open(tmp, "rb") as fh:
            os.fsync(fh.fileno())
    except OSError:
        # fsync isn't supported on every filesystem (Windows FAT, some
        # network mounts). Best-effort; the write already flushed via
        # write_text's close.
        pass

    try:
        tmp_dev = os.stat(tmp.parent).st_dev
        target_dev = os.stat(target.parent).st_dev
        same_volume = tmp_dev == target_dev
    except OSError:
        same_volume = True  # optimistic; os.replace will raise if truly cross-volume

    if same_volume:
        os.replace(str(tmp), str(target))
    else:
        print(
            f"WARNING: atomic write not possible - {tmp} and {target} are on "
            f"different volumes. Falling back to shutil.move (non-atomic).",
            file=sys.stderr,
        )
        shutil.move(str(tmp), str(target))


# ---------------------------------------------------------------------------
# Public: write_sidecars
# ---------------------------------------------------------------------------


def write_sidecars(
    engagement_dir: Path,
    result: DedupeResult,
    candidates: List[dict],
    finding_groups: List[dict],
    device: str,
    priority_path_stories: "List[dict] | None" = None,
) -> None:
    """Write the JSON sidecar files for a device.

    Files written:
    - dedup-review{suffix}.json
    - priority-path-candidates{suffix}.json
    - finding-groups{suffix}.json
    - priority-path-stories{suffix}.json   (only when priority_path_stories
                                             is non-empty — the validated
                                             synthesizer output in its
                                             canonical Story shape)

    Where suffix is "" for laptop, "-{device}" for others.

    ``priority-path-stories{suffix}.json`` is the H1 fix: the renderer
    used to re-parse the Priority Path from markdown, which drifted from
    the validated story objects and let hand-edited audit.md smuggle
    bogus F-N refs past the validator. The sidecar carries the validated
    payload verbatim, and the renderer prefers it over markdown parsing.
    Markdown parsing stays as a fallback for legacy engagements written
    before this sidecar existed.
    """
    suffix = _sidecar_suffix(device)

    def _write_json(filename: str, data: object) -> None:
        path = engagement_dir / filename
        text = json.dumps(data, indent=2, ensure_ascii=False)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    # dedup-review
    dedup_data = {
        "auto_merged": result.auto_merged,
        "fuzzy_candidates": result.fuzzy_candidates,
    }
    _write_json(f"dedup-review{suffix}.json", dedup_data)

    # priority-path-candidates
    _write_json(f"priority-path-candidates{suffix}.json", candidates)

    # finding-groups
    _write_json(f"finding-groups{suffix}.json", finding_groups)

    # priority-path-stories (only if the synthesizer ran and stories
    # validated — empty or None means no sidecar, renderer falls back
    # to markdown parsing for the Priority Path).
    if priority_path_stories:
        _write_json(
            f"priority-path-stories{suffix}.json",
            {"stories": priority_path_stories},
        )
