"""Phase F.3 deterministic helpers for synthesizer dispatch.

The synthesizer (Layer 3) is a single Opus call that reads all cluster
emissions, ethics findings, both batons, screenshots, and emits the two
audit documents plus the structured synthesizer-emission-v1.json. This
module provides the three deterministic helpers that gate the dispatch:

1. ``trim_baton_to_referenced_elements`` - shrink a baton to only the
   elements specialists actually cited. Cuts payload ~70% on real PDPs;
   avoids 1M-context overflow on monster pages with 500+ baton elements.
   Mandatory before synthesizer dispatch per Phase F.3.

2. ``compute_phrasing_seeds`` - build the {{phrasing_seeds_block}} prose
   the lead injects into degraded-mode per-device dispatch prompts. The
   seeds are specialist-emitted observation/recommendation/why_this_matters
   text concatenated into one markdown block; the synthesizer is told to
   render scope='page' findings using the seeds verbatim so both per-device
   audit documents emerge with byte-identical scope='page' rendering.

3. ``levenshtein_ratio`` and ``assert_synchronization_invariant`` - the
   post-emission cross-device drift gate. Computes Levenshtein edit
   distance between the two audit documents on each scope='page' finding's
   rendered prose; asserts every ratio is <=0.10 (10% threshold per Phase
   F.3 of the canonical plan). Failure triggers
   ``engagement_status: failed_synthesis_drift`` and the lead writes
   lead-reflection.md.

Authored 2026-04-27 as Phase F.3 deliverable. See:
- docs/plans/2026-04-27-feat-ecp-v2-redesign-plan.md Phase F.3
- contracts/synthesizer-v2.md (cross-device synchronization rule)
- schema/synthesizer-emission-v1.json (failed_synthesis_drift status)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

from .atomic_write import atomic_write_json
from .models import Finding


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Phase F.3 cross-device drift threshold. Levenshtein ratio <=10% is
# effectively byte-identical with whitespace/punctuation flexibility. Single-
# shot dispatch produces 0% ratio; degraded-mode per-device dispatch with
# phrasing seeds should also approach 0% but the threshold absorbs minor
# Sonnet-vs-Opus model variation.
SYNCHRONIZATION_THRESHOLD = 0.10

# Paragraph headers the synthesizer emits per finding (per the
# contracts/synthesizer-v2.md one-shot example structure). The Levenshtein
# extraction matches against these to slice each finding's rendered prose.
_OBSERVATION_HEADER = "**OBSERVATION:**"
_RECOMMENDATION_HEADER = "**RECOMMENDATION:**"
_WHY_HEADER = "**Why this matters:**"


# ---------------------------------------------------------------------------
# 1. Baton pre-trim
# ---------------------------------------------------------------------------


def collect_referenced_e_indexes(findings: Iterable[Finding]) -> set[str]:
    """Return the set of baton e_indexes any finding references.

    Sources:
    - finding.baton_index (when not 'absent')
    - finding.evidence_anchors[].reference for type='dom' anchors that match
      the e<int> pattern

    'absent' baton_indexes are NOT included (they intentionally don't
    reference a real element). CSS-selector dom anchors (rare; only emitted
    by specialists when a finding's element has no e_index in the baton)
    are also skipped.
    """
    referenced: set[str] = set()
    e_index_re = re.compile(r"^e[0-9]+$")
    for f in findings:
        if f.baton_index and f.baton_index != "absent" and e_index_re.match(f.baton_index):
            referenced.add(f.baton_index)
        for anchor in f.evidence_anchors or ():
            if anchor.type in ("dom", "both") and anchor.reference and e_index_re.match(anchor.reference):
                referenced.add(anchor.reference)
    return referenced


def trim_baton_to_referenced_elements(
    baton: dict,
    referenced_e_indexes: set[str],
) -> dict:
    """Return a new baton dict with elements[] filtered to referenced e_indexes.

    Preserves all other top-level fields (schema_version, engagement_id,
    device, url, captured_at, viewport, capture_state, sections, page_head,
    etc.) and only filters the elements[] array. The trimmed baton still
    validates against schema/baton-v1.json because every required field
    survives.

    Section-level rendering still works: ``sections[].slug`` references
    remain valid (sections are not element-level). ``baton.elements`` becomes
    a small list of just the elements specialists cited.

    Determinism: the filtered list preserves the original element order
    (DOM order in the baton). Same input -> same output across runs.
    """
    if not isinstance(baton, dict):
        raise TypeError(f"baton must be a dict, got {type(baton).__name__}")
    elements = baton.get("elements") or []
    kept = [el for el in elements if el.get("e_index") in referenced_e_indexes]
    # Shallow-copy the baton with the filtered elements substituted.
    trimmed = dict(baton)
    trimmed["elements"] = kept
    return trimmed


def build_trim_summary(
    baton: dict,
    kept_e_indexes: set[str],
) -> dict:
    """Build a sidecar summary describing what the trim helper kept vs removed.

    The trimmed baton (output of ``trim_baton_to_referenced_elements``) only
    carries the kept elements. Downstream readers — the synthesizer especially —
    cannot tell what else existed on the page. This becomes a real evidence gap:
    e.g., the pricing-mobile F-5 "payment icons absent from purchase zone"
    finding on the awdmods 2026-05-18 run cited the absence of footer payment
    icons (e22..e29), but those e_indexes were trimmed before the synthesizer
    saw them, so the synth had to take the finding on faith.

    The summary surfaces an inventory the synth can reference by name without
    needing an ``e_index`` citation: kept counts by role, removed counts by
    role, and a compact removed-elements list with the most useful identifying
    fields. Schema is intentionally small so a 30-element baton produces a
    few-KB sidecar.

    Output shape (stable; tests pin this):

        {
          "engagement_id": "<from baton>",
          "device": "<from baton>",
          "input_element_count": <int>,
          "output_element_count": <int>,
          "trim_ratio": <0.0-1.0>,
          "kept_e_indexes": ["e0", "e3", ...],   # sorted
          "removed": [
            {
              "e_index": "e1",
              "tag": "img",
              "role": "image",
              "accessible_name_truncated": "...",
              "scroll_y": 1234
            },
            ...
          ],
          "counts_by_role": {
            "kept":    {"button": 2, "image": 3, ...},
            "removed": {"button": 1, "navigation": 1, ...}
          }
        }

    Determinism: same baton + same kept set produce byte-identical summary
    across runs. ``kept_e_indexes`` is sorted; ``removed`` preserves the
    original DOM-order from the baton.

    See contracts/lead-discipline.md (filesystem write atomicity) and the
    Phase 5 acceptance criterion in
    docs/ecp/2026-05-18-report-accuracy-and-hotspot-remediation-plan.md:
    "A future operator can explain why an element was trimmed."
    """
    elements = baton.get("elements") or []
    kept: list[dict] = []
    removed: list[dict] = []
    for el in elements:
        e_index = el.get("e_index")
        if e_index in kept_e_indexes:
            kept.append(el)
        else:
            accessible_name = el.get("accessible_name") or ""
            if len(accessible_name) > 80:
                accessible_name = accessible_name[:77] + "..."
            removed.append({
                "e_index": e_index,
                "tag": el.get("tag", ""),
                "role": el.get("role", ""),
                "accessible_name_truncated": accessible_name,
                "scroll_y": (el.get("rect") or {}).get("y", 0),
            })

    def _by_role(items: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for it in items:
            role = it.get("role") or it.get("tag") or "unknown"
            counts[role] = counts.get(role, 0) + 1
        return dict(sorted(counts.items()))

    input_count = len(elements)
    output_count = len(kept)
    return {
        "engagement_id": baton.get("engagement_id", ""),
        "device": baton.get("device", ""),
        "input_element_count": input_count,
        "output_element_count": output_count,
        "trim_ratio": (output_count / input_count) if input_count > 0 else 1.0,
        "kept_e_indexes": sorted(
            kept_e_indexes,
            key=lambda x: int(x[1:]) if x.startswith("e") and x[1:].isdigit() else 9999,
        ),
        "removed": removed,
        "counts_by_role": {
            "kept": _by_role(kept),
            "removed": _by_role(removed),
        },
    }


def trim_baton_file(
    baton_path: Path | str,
    findings: Iterable[Finding],
    out_path: Path | str,
    summary_path: Path | str | None = None,
) -> dict:
    """Read a baton file, trim it to referenced elements, atomically write.

    When ``summary_path`` is provided, also writes a ``baton-{device}-trimmed-
    summary.json`` sidecar (see ``build_trim_summary``) so downstream readers
    can inspect what was removed without re-loading the full baton. When
    ``summary_path`` is None, only the trimmed baton is written (legacy
    behavior preserved for existing callers).

    Returns the trim summary dict for logging. When the sidecar was written,
    the returned dict also includes ``summary_path``.

    Use this in the lead orchestration before synthesizer dispatch so the
    {{desktop_baton_path}} / {{mobile_baton_path}} placeholders in the
    synthesizer prompt point at trimmed batons.
    """
    baton_path = Path(baton_path)
    out_path = Path(out_path)
    baton = json.loads(baton_path.read_text(encoding="utf-8"))
    referenced = collect_referenced_e_indexes(findings)
    trimmed = trim_baton_to_referenced_elements(baton, referenced)
    atomic_write_json(out_path, trimmed)
    input_count = len(baton.get("elements") or [])
    output_count = len(trimmed["elements"])
    result = {
        "input_count": input_count,
        "output_count": output_count,
        "trim_ratio": (output_count / input_count) if input_count > 0 else 1.0,
        "out_path": str(out_path),
    }
    if summary_path is not None:
        summary_path = Path(summary_path)
        summary = build_trim_summary(baton, referenced)
        atomic_write_json(summary_path, summary)
        result["summary_path"] = str(summary_path)
    return result


# ---------------------------------------------------------------------------
# 2. Phrasing-seed manifest for degraded-mode dispatch
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PhrasingSeed:
    """One scope='page' finding's pre-computed prose for degraded-mode dispatch.

    The lead concatenates these into the {{phrasing_seeds_block}} placeholder
    in synthesizer-v2.md; the synthesizer renders the seeds verbatim into
    both per-device audit documents.
    """

    f_ref: str  # "{cluster} F-{NN}"
    title: str
    observation: str
    recommendation: str
    why_this_matters: str

    def render_markdown(self) -> str:
        """Render this seed as a markdown block the synthesizer copies verbatim.

        The structure mirrors the per-finding block in audit-{device}.md
        ('### F-NN - <title>' followed by OBSERVATION / RECOMMENDATION /
        Why this matters paragraphs). The synthesizer pastes the rendered
        markdown into both audit documents under the appropriate cluster
        section.
        """
        return (
            f"### {self.f_ref} - {self.title}\n"
            f"\n"
            f"{_OBSERVATION_HEADER} {self.observation}\n"
            f"\n"
            f"{_RECOMMENDATION_HEADER} {self.recommendation}\n"
            f"\n"
            f"{_WHY_HEADER} {self.why_this_matters}\n"
        )


def _f_ref_for(finding: Finding) -> str:
    """Build the '{cluster} F-{NN}' reference string for a finding.

    Uses display_index when set (post-pipeline assignment) and local_index
    as the fallback (pre-display-index assignment, e.g., directly from
    json_parser.parse_emission_file output). The Phase F.4 parser
    enforces resolution against the finalized FinalizedFindings.valid_refs(),
    not these strings - this helper is used for seed authoring only.
    """
    idx = finding.display_index if finding.display_index else finding.local_index
    return f"{finding.cluster} F-{idx:02d}"


def compute_phrasing_seeds(findings: Sequence[Finding]) -> List[PhrasingSeed]:
    """Build the deterministic phrasing seeds for scope='page' findings.

    Selects every finding with scope='page', orders them by
    (priority_rank, evidence_tier_rank desc, confidence desc, cluster, local_index)
    so the manifest is byte-identical across runs given the same input. The
    ordering is the same the canonical plan describes for Phase F.3 step 1.

    The lead injects the rendered seeds (one per finding, joined with blank
    lines) into the {{phrasing_seeds_block}} placeholder of the synthesizer
    template body for degraded-mode per-device dispatch.

    Returns a list of PhrasingSeed instances. Empty list valid (page may
    have zero scope='page' findings, though unusual on real PDPs).
    """
    page_findings = [f for f in findings if f.scope == "page"]

    # Ordering: priority (CRITICAL=0..LOW=3) ascending, then evidence tier
    # rank descending (Gold=3..Bronze=1), then confidence descending, then
    # cluster ascending, then local_index ascending. Stable across runs.
    from .models import EVIDENCE_TIER_RANK

    def sort_key(f: Finding):
        tier_rank = EVIDENCE_TIER_RANK.get(f.tier, 0)
        confidence = f.confidence if f.confidence is not None else 0.0
        return (
            f.priority_rank,
            -tier_rank,
            -confidence,
            f.cluster,
            f.local_index,
        )

    page_findings_sorted = sorted(page_findings, key=sort_key)

    return [
        PhrasingSeed(
            f_ref=_f_ref_for(f),
            title=f.title,
            observation=f.observation,
            recommendation=f.recommendation,
            why_this_matters=f.why_matters,
        )
        for f in page_findings_sorted
    ]


def render_phrasing_seeds_block(seeds: Sequence[PhrasingSeed]) -> str:
    """Concatenate seeds into the markdown block injected into the prompt.

    Empty seeds list returns empty string (single-shot mode; the synthesizer
    sees an empty block and writes all prose itself). Non-empty seeds list
    returns a markdown-formatted manifest the synthesizer is instructed to
    use verbatim for scope='page' findings.
    """
    if not seeds:
        return ""
    parts = ["The following scope='page' findings have pre-computed phrasing. Use the OBSERVATION + RECOMMENDATION + 'Why this matters' text VERBATIM in both per-device audit documents:\n"]
    parts.extend(seed.render_markdown() for seed in seeds)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 3. Levenshtein cross-device synchronization gate
# ---------------------------------------------------------------------------


def levenshtein_distance(a: str, b: str) -> int:
    """Compute classic Levenshtein edit distance between two strings.

    Pure-Python implementation - no third-party dependency. O(n*m) time,
    O(min(n,m)) space (rolling row optimization). Adequate for prose
    paragraphs <=2000 chars; the synchronization gate runs <100 times per
    audit so the overall cost is negligible vs LLM dispatch.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    # Ensure b is the shorter to minimize memory.
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            insertions = previous[j] + 1
            deletions = current[j - 1] + 1
            substitutions = previous[j - 1] + (0 if ca == cb else 1)
            current[j] = min(insertions, deletions, substitutions)
        previous = current
    return previous[-1]


def levenshtein_ratio(a: str, b: str) -> float:
    """Return Levenshtein distance / max(len(a), len(b)).

    Returns 0.0 for identical strings, 1.0 for completely disjoint strings,
    NaN-equivalent (0.0) for two empty strings (no drift to measure).

    The ratio is what the Phase F.3 assertion gates on. <=0.10 means
    effectively byte-identical with whitespace/punctuation tolerance.
    """
    if a == b:
        return 0.0
    longest = max(len(a), len(b))
    if longest == 0:
        return 0.0
    return levenshtein_distance(a, b) / longest


def extract_finding_prose(
    audit_md: str,
    f_ref: str,
) -> tuple[str, str, str] | None:
    """Extract OBSERVATION / RECOMMENDATION / why-this-matters paragraphs for f_ref.

    The audit document renders each finding under a heading like:
        ### {cluster} F-{NN} - <title>

        **OBSERVATION:** <text>

        **RECOMMENDATION:** <text>

        **Why this matters:** <text>

    Returns (observation, recommendation, why_this_matters) tuples of
    stripped strings, or None if the finding's heading isn't found in the
    document. Stripping normalizes trailing newlines + ambient whitespace
    so the Levenshtein ratio measures prose drift, not formatting drift.
    """
    # Match '### {cluster} F-NN' on its own line; pin to start-of-line.
    # Permissive: accept 3+ hashes (synthesizer may nest findings as level-4
    # under level-3 cluster sections) and case-insensitive cluster slug
    # (TitleCase headings read better in customer-facing prose; the f_ref
    # contract in the JSON stays lowercase per schema).
    heading_re = re.compile(
        rf"^#{{3,4}}\s+{re.escape(f_ref)}\b.*?$",
        re.MULTILINE | re.IGNORECASE,
    )
    m = heading_re.search(audit_md)
    if not m:
        return None

    # Slice from the heading to the next finding heading (3-4 hashes) OR any
    # section heading (2-4 hashes), whichever comes first.
    #
    # G18 (2026-05-27): pre-fix this matched ONLY finding headings, so the
    # LAST finding's body slice ran to EOF and absorbed any trailing
    # per-device `## Methodology Notes` section — producing a false-positive
    # drift result when only the trailing section differed. Both Run
    # 2026-05-27-af72a2ae and Run 2026-05-27-52f53a53 lead-reflections
    # independently flagged the same root cause and proposed the same fix.
    # Matching `^#{2,4}\s+\S+` catches BOTH finding headings (3-4 hashes,
    # `### pricing F-01`) AND non-finding section headings (2-3 hashes,
    # `## Methodology Notes`), so the slice terminates at the first
    # following heading of any kind.
    start = m.end()
    next_re = re.compile(r"^#{2,4}\s+\S+", re.MULTILINE)
    next_match = next_re.search(audit_md, pos=start)
    end = next_match.start() if next_match else len(audit_md)
    body = audit_md[start:end]

    # Within the body, find the three labeled paragraphs.
    obs = _slice_section(body, _OBSERVATION_HEADER)
    rec = _slice_section(body, _RECOMMENDATION_HEADER)
    why = _slice_section(body, _WHY_HEADER)
    if obs is None or rec is None or why is None:
        return None
    return obs, rec, why


def _slice_section(body: str, header: str) -> str | None:
    """Return the prose between ``header`` and the next bold header or end.

    Strips leading/trailing whitespace from the slice. Returns None if the
    header isn't found.

    G18 (2026-05-27): the terminator also stops at any markdown heading
    (`\n##` / `\n###` / `\n####`) so a stray section heading inside the
    body can't pollute the slice. The upstream ``extract_finding_prose``
    fix already excludes section headings from the body it builds, so
    this is a defensive belt-and-suspenders layer — if a future change
    relaxes the upstream slice, ``_slice_section`` still won't pull in
    a trailing section.
    """
    idx = body.find(header)
    if idx < 0:
        return None
    after = idx + len(header)
    # Find the next bold header (lookahead for '\n\n**' patterns), the next
    # markdown heading (lookahead for `\n##` ... `\n####`), or eof.
    next_re = re.compile(r"\n\n\*\*[A-Z]|\n#{2,4}\s+\S+")
    m = next_re.search(body, pos=after)
    end = m.start() if m else len(body)
    return body[after:end].strip()


@dataclass(frozen=True)
class DriftReport:
    """Report from ``assert_synchronization_invariant``.

    Records every scope='page' finding's per-paragraph drift ratios so the
    lead can write lead-reflection.md with diagnostic detail when the
    assertion fails. ``ok`` is the overall verdict.
    """

    ok: bool
    threshold: float
    max_ratio: float
    per_finding: tuple[tuple[str, float, float, float], ...]  # (f_ref, obs_ratio, rec_ratio, why_ratio)
    missing: tuple[str, ...]  # f_refs whose prose wasn't found in one or both docs


def assert_synchronization_invariant(
    desktop_md: str,
    mobile_md: str,
    scope_page_refs: Sequence[str],
    threshold: float = SYNCHRONIZATION_THRESHOLD,
) -> DriftReport:
    """Verify scope='page' findings render consistently across device docs.

    For every f_ref in scope_page_refs, extract the OBSERVATION /
    RECOMMENDATION / why-this-matters paragraphs from both audit documents
    and compute Levenshtein ratios. ``ok`` is True iff every per-paragraph
    ratio is <=threshold AND every f_ref's prose was extractable from
    BOTH documents.

    The lead invokes this after synthesizer dispatch (single-shot or
    degraded-mode). On ``ok=False``, the lead writes lead-reflection.md
    with the per-finding ratios and aborts the engagement with
    ``engagement_status: failed_synthesis_drift``.
    """
    per_finding: list[tuple[str, float, float, float]] = []
    missing: list[str] = []
    max_ratio = 0.0
    for f_ref in scope_page_refs:
        d_prose = extract_finding_prose(desktop_md, f_ref)
        m_prose = extract_finding_prose(mobile_md, f_ref)
        if d_prose is None or m_prose is None:
            missing.append(f_ref)
            continue
        obs_ratio = levenshtein_ratio(d_prose[0], m_prose[0])
        rec_ratio = levenshtein_ratio(d_prose[1], m_prose[1])
        why_ratio = levenshtein_ratio(d_prose[2], m_prose[2])
        max_ratio = max(max_ratio, obs_ratio, rec_ratio, why_ratio)
        per_finding.append((f_ref, obs_ratio, rec_ratio, why_ratio))

    ok = (not missing) and (max_ratio <= threshold)
    return DriftReport(
        ok=ok,
        threshold=threshold,
        max_ratio=max_ratio,
        per_finding=tuple(per_finding),
        missing=tuple(missing),
    )


__all__ = [
    "DriftReport",
    "PhrasingSeed",
    "SYNCHRONIZATION_THRESHOLD",
    "assert_synchronization_invariant",
    "build_trim_summary",
    "collect_referenced_e_indexes",
    "compute_phrasing_seeds",
    "extract_finding_prose",
    "levenshtein_distance",
    "levenshtein_ratio",
    "render_phrasing_seeds_block",
    "trim_baton_file",
    "trim_baton_to_referenced_elements",
]
