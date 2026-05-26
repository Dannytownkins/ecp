#!/usr/bin/env python3
"""test-specialist.py — Split-mode harness for v2 specialist + synthesizer dispatch.

The Anthropic API isn't reachable from Claude Code Max plan, and Python scripts
can't directly invoke Claude Code's Agent/Task primitive. This harness fills the
gap with four modes:

  prepare              Render the canonical specialist prompt for a
                       (cluster, device, engagement) tuple. The lead pipes
                       stdout into an Agent dispatch via the Claude Code tool
                       surface.

  validate             Validate a specialist's cluster-emission-v1.json against
                       schema/cluster-emission-v1.json (which $refs
                       schema/finding-v1.json) plus business rules. Pass
                       --schema synthesizer-emission to instead validate a
                       synthesizer-emission-v1.json against
                       schema/synthesizer-emission-v1.json + the JSON-derived
                       allowlist (Phase F.4). On failure emits a retry prompt.

  prepare-synthesizer  Render the synthesizer dispatch prompt for an
                       engagement (Phase F.2). Substitutes per-engagement
                       variables (paths, viewports, screenshots) into the
                       contracts/synthesizer-v2.md template body.

  drift-check          Run the cross-device synchronization assertion (Phase
                       F.3) on already-emitted audit-{device}.md files for
                       the scope='page' f_refs declared in the synthesizer
                       emission. Reports max Levenshtein ratio and aborts
                       with non-zero exit code if it exceeds the threshold.

Authored 2026-04-27 as Phase B.3 deliverable; Phase F.4 added synthesizer
support. See:
- docs/plans/2026-04-27-feat-ecp-v2-redesign-plan.md Phase B + Phase F
- contracts/specialist-prompt-v2.md (specialist template)
- contracts/synthesizer-v2.md (synthesizer template)
- contracts/specialists/pricing.md (per-cluster parameter file)
- schema/cluster-emission-v1.json + schema/finding-v1.json (specialist surface)
- schema/synthesizer-emission-v1.json (synthesizer surface)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

# Add scripts/ to sys.path so atomic_write is importable for retry-prompt writes.
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from assembly.atomic_write import atomic_write_text  # noqa: E402
from assembly.business_rules import (  # noqa: E402
    BusinessRuleViolation,
    FindingBand,
    build_retry_prompt as _br_build_retry_prompt,
    validate_business_rules as _br_validate_business_rules,
)


# ---------------------------------------------------------------------------
# Cluster slug + valid emission targets
# ---------------------------------------------------------------------------

VALID_CLUSTERS = {
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
}

VALID_DEVICES = {"desktop", "mobile"}


# ---------------------------------------------------------------------------
# Markdown section extraction (small, focused — avoids a yaml/markdown dep)
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^```([a-zA-Z0-9_-]*)\n(.*?)\n```", re.DOTALL | re.MULTILINE)
_FENCE_4_RE = re.compile(r"^````([a-zA-Z0-9_-]*)\n(.*?)\n````", re.DOTALL | re.MULTILINE)


def _extract_fenced_blocks(text: str) -> list[tuple[str, str]]:
    """Return a list of (lang, body) tuples for every 3-backtick fenced block."""
    return [(m.group(1), m.group(2)) for m in _FENCE_RE.finditer(text)]


def _extract_fenced_blocks_4(text: str) -> list[tuple[str, str]]:
    """Return (lang, body) tuples for every 4-backtick fenced block.

    The template body in specialist-prompt-v2.md uses 4-backtick outer fences
    so 3-backtick inner fences (file-path samples, JSON example) are preserved.
    """
    return [(m.group(1), m.group(2)) for m in _FENCE_4_RE.finditer(text)]


def _extract_section(text: str, heading: str) -> str:
    """Return the markdown body between '## {heading}' and the next '## ' heading.

    Returns empty string if heading not found.
    """
    pattern = re.compile(
        r"^##\s+" + re.escape(heading) + r"\s*\n(.*?)(?=^##\s|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    m = pattern.search(text)
    return m.group(1) if m else ""


def _parse_yaml_subset(yaml_text: str) -> dict[str, Any]:
    """Parse the tiny subset of YAML used in specialist parameter blocks.

    Supports: scalar `key: value` and `key:` followed by `  - item` list lines.
    Does NOT support nested mappings, anchors, multiline scalars. Hand-rolled so
    PyYAML is not pulled in just for two fields.
    """
    out: dict[str, Any] = {}
    current_list_key: str | None = None
    for raw_line in yaml_text.splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - ") and current_list_key is not None:
            out[current_list_key].append(line[4:].strip())
            continue
        # Top-level key
        if not line.startswith(" "):
            current_list_key = None
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value == "":
                # List follows
                out[key] = []
                current_list_key = key
            else:
                out[key] = value
    return out


# ---------------------------------------------------------------------------
# Specialist parameter loading
# ---------------------------------------------------------------------------


def load_specialist_params(cluster: str) -> dict[str, Any]:
    """Load per-cluster parameters from contracts/specialists/{cluster}.md.

    Returns {cluster, references, guidance_block, reference_file_list}.
    Raises FileNotFoundError if the per-cluster file does not exist.
    """
    if cluster not in VALID_CLUSTERS:
        raise ValueError(f"Unknown cluster slug: {cluster!r}. Valid: {sorted(VALID_CLUSTERS)}")
    path = REPO_ROOT / "contracts" / "specialists" / f"{cluster}.md"
    if not path.is_file():
        raise FileNotFoundError(
            f"contracts/specialists/{cluster}.md does not exist. "
            f"Phase B authors only pricing.md; other clusters land in Phase C."
        )
    text = path.read_text(encoding="utf-8")

    blocks = _extract_fenced_blocks(text)
    yaml_blocks = [b for lang, b in blocks if lang == "yaml"]
    if not yaml_blocks:
        raise ValueError(f"{path}: expected a yaml fenced block with cluster + references")
    params = _parse_yaml_subset(yaml_blocks[0])
    if params.get("cluster") != cluster:
        raise ValueError(
            f"{path}: yaml cluster={params.get('cluster')!r} disagrees with filename {cluster!r}"
        )
    references = params.get("references") or []
    if not references:
        raise ValueError(f"{path}: yaml references list is empty")

    # Cluster guidance: the second-or-later non-yaml fenced block, located inside
    # "## Cluster guidance" section. Pull the block as-is (the prompt template
    # interpolates it verbatim into {{cluster_guidance}}).
    guidance_section = _extract_section(text, "Cluster guidance")
    guidance_blocks = [b for lang, b in _extract_fenced_blocks(guidance_section) if lang == ""]
    guidance_block = guidance_blocks[0] if guidance_blocks else ""

    # Reference file list block (rendered into {{reference_file_list}}). If the
    # specialist file ships one, use it; otherwise synthesize from references[].
    ref_list_section = _extract_section(text, "Reference file list (rendered into template)")
    ref_list_blocks = [b for lang, b in _extract_fenced_blocks(ref_list_section) if lang == ""]
    if ref_list_blocks:
        reference_file_list = ref_list_blocks[0]
    else:
        reference_file_list = "\n".join(f"- `{r}.md`" for r in references)

    # Phase L: surface_vocabulary (closed list) + target_finding_count (band)
    surface_vocabulary: list[str] = params.get("surface_vocabulary") or []
    target_finding_count_raw: str = params.get("target_finding_count") or ""
    target_band: FindingBand | None = None
    if target_finding_count_raw:
        try:
            target_band = FindingBand.parse(target_finding_count_raw)
        except (ValueError, AttributeError):
            target_band = None  # malformed — silently skip; lead can warn

    return {
        "cluster": cluster,
        "references": references,
        "guidance_block": guidance_block,
        "reference_file_list": reference_file_list,
        "surface_vocabulary": surface_vocabulary,
        "target_band": target_band,
    }


def render_surface_vocabulary_block(
    cluster: str, vocabulary: list[str]
) -> str:
    """Render the surface_vocabulary YAML list as a <surface_vocabulary> XML compartment.

    Substituted into the {{cluster_surface_vocabulary}} slot in the dispatched
    prompt. The compartment instructs the specialist on the closed vocabulary
    rule per contracts/specialist-prompt-v2.md "## Determinism contract".
    """
    if not vocabulary:
        # No vocab configured for this cluster — render an empty compartment
        # with a note. Validator's cluster_vocab=None branch will skip the
        # check, so this matches runtime behavior.
        return (
            "<surface_vocabulary>\n"
            "(no surface_vocabulary configured for this cluster — surface field is unconstrained)\n"
            "</surface_vocabulary>"
        )
    bullets = "\n".join(f"- {slug}" for slug in vocabulary)
    return (
        "<surface_vocabulary>\n"
        f"Closed list of abstract surfaces audited by the {cluster} cluster.\n"
        "Your finding's `surface` field MUST be one of:\n"
        "1. A slug from the list below, OR\n"
        "2. A `sections[].slug` from your baton (always valid — describes what's on the page), OR\n"
        "3. The literal string `\"other\"`, paired with a non-empty `surface_note` ≤ 240 chars\n"
        "   explaining what concept the cluster vocabulary should grow to cover.\n"
        "\n"
        "Inventing a surface outside this set bounces your emission for retry.\n"
        "\n"
        f"{bullets}\n"
        "</surface_vocabulary>"
    )


# ---------------------------------------------------------------------------
# Template body extraction
# ---------------------------------------------------------------------------


def load_template_body() -> str:
    """Extract the dispatch prompt template body from specialist-prompt-v2.md.

    The template body is the (single) 4-backtick outer fenced block in the
    document. The 4-backtick fence preserves 3-backtick inner fences
    (file-path samples, JSON example) as content. We search the whole file
    rather than the '## Template body' section because the template body
    contains inner '##' subheadings (Role, Inputs, Output contract, etc.)
    that would prematurely close a section-scoped extraction.
    """
    return _load_4backtick_template(REPO_ROOT / "contracts" / "specialist-prompt-v2.md")


def load_synthesizer_template_body() -> str:
    """Extract the synthesizer dispatch prompt template body from synthesizer-v2.md.

    Mirror of load_template_body() for the Phase F.2 synthesizer prompt.
    """
    return _load_4backtick_template(REPO_ROOT / "contracts" / "synthesizer-v2.md")


def _load_4backtick_template(path: Path) -> str:
    """Shared 4-backtick template-body extractor used for both v2 prompt docs."""
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found.")
    text = path.read_text(encoding="utf-8")
    blocks = [b for lang, b in _extract_fenced_blocks_4(text) if lang == ""]
    if not blocks:
        raise ValueError(f"{path}: no 4-backtick fenced template body found")
    if len(blocks) > 1:
        raise ValueError(
            f"{path}: expected exactly one 4-backtick fenced template body,"
            f" found {len(blocks)}"
        )
    return blocks[0]


# ---------------------------------------------------------------------------
# prepare mode — render dispatch prompt
# ---------------------------------------------------------------------------


def render_prompt(
    *,
    cluster: str,
    device: str,
    engagement_id: str,
    cluster_context_path: str,
    baton_path: str,
    viewport_width: int,
    viewport_height: int,
    dpr: float,
    page_type: str,
    platform: str,
    screenshot_paths: list[str],
) -> str:
    if cluster not in VALID_CLUSTERS:
        raise ValueError(f"Unknown cluster: {cluster!r}")
    if device not in VALID_DEVICES:
        raise ValueError(f"Unknown device: {device!r}; expected one of {sorted(VALID_DEVICES)}")

    params = load_specialist_params(cluster)
    template = load_template_body()

    screenshot_block = "\n".join(f"  - `{p}`" for p in screenshot_paths) if screenshot_paths else "  (no screenshots provided)"

    surface_vocab_block = render_surface_vocabulary_block(
        cluster, params.get("surface_vocabulary") or []
    )

    substitutions = {
        "{{cluster}}": cluster,
        "{{device}}": device,
        "{{engagement_id}}": engagement_id,
        "{{cluster_context_path}}": cluster_context_path,
        "{{baton_path}}": baton_path,
        "{{viewport_width}}": str(viewport_width),
        "{{viewport_height}}": str(viewport_height),
        "{{dpr}}": str(dpr),
        "{{page_type}}": page_type,
        "{{platform}}": platform,
        "{{reference_file_list}}": params["reference_file_list"],
        "{{cluster_guidance}}": params["guidance_block"],
        "{{cluster_surface_vocabulary}}": surface_vocab_block,
        "{{screenshot_paths_with_descriptions}}": screenshot_block,
    }

    rendered = template
    for needle, replacement in substitutions.items():
        rendered = rendered.replace(needle, replacement)

    # Sanity check: no unsubstituted {{...}} placeholders remain.
    leftover = re.findall(r"\{\{[a-zA-Z_][a-zA-Z_0-9]*\}\}", rendered)
    if leftover:
        raise ValueError(f"Unresolved template placeholders: {sorted(set(leftover))}")

    return rendered


# ---------------------------------------------------------------------------
# prepare-synthesizer mode — render synthesizer dispatch prompt
# ---------------------------------------------------------------------------


def build_canonical_f_refs_block(data: dict) -> str:
    """Format the canonical f_refs JSON as a markdown manifest for the prompt.

    Input shape (built by the lead's Layer-2 finalize step):
    {
      "valid_refs": ["pricing F-01", "trust-credibility F-12", ...],
      "by_canonical_ref": {
        "pricing F-01": {
          "title": "No MSRP Anchor on Price Block",
          "scope": "page",          # "page" | "device"
          "device": "page",          # "page" | "desktop" | "mobile"
          "devices_present": ["desktop", "mobile"],   # which device emissions surfaced this finding
          "verdict": "FAIL",
          "severity": "HIGH"
        },
        ...
      }
    }

    Output: markdown table grouping refs by cluster, with one row per canonical ref
    naming title, scope, devices_present, severity. Compact; the synthesizer reads
    this once and uses it as the f_ref source of truth.
    """
    by_ref = data.get("by_canonical_ref") or {}
    if not by_ref:
        return "  (no canonical f_refs supplied — this is a bug; the lead must always provide the manifest)"

    by_cluster: dict[str, list[tuple[str, dict]]] = {}
    for ref, meta in by_ref.items():
        cluster = ref.split(" F-")[0] if " F-" in ref else "unknown"
        by_cluster.setdefault(cluster, []).append((ref, meta))

    lines: list[str] = []
    lines.append("Use ONLY these f_refs in priority_path[].f_refs, scope_page_synchronized_refs, "
                 "quick_wins_manifest, severity_manifest, and as the heading suffix on each "
                 "finding subsection. Each row shows: canonical ref, title, scope, devices the "
                 "finding was surfaced on, severity.\n")
    for cluster in sorted(by_cluster.keys()):
        lines.append(f"\n**{cluster}** ({len(by_cluster[cluster])} findings)")
        lines.append("")
        lines.append("| f_ref | title | scope | devices | severity |")
        lines.append("|---|---|---|---|---|")
        for ref, meta in sorted(by_cluster[cluster], key=lambda kv: kv[0]):
            title = (meta.get("title") or "").replace("|", "\\|")[:80]
            scope = meta.get("scope") or "?"
            devices = ",".join(meta.get("devices_present") or [])
            severity = meta.get("severity") or meta.get("verdict") or "?"
            lines.append(f"| `{ref}` | {title} | {scope} | {devices} | {severity} |")
    return "\n".join(lines)


def render_synthesizer_prompt(
    *,
    engagement_id: str,
    cluster_emission_paths: list[str],
    ethics_findings_path: str,
    desktop_baton_path: str,
    mobile_baton_path: str,
    desktop_screenshot_paths: list[str],
    mobile_screenshot_paths: list[str],
    desktop_viewport: str,
    mobile_viewport: str,
    page_type: str,
    platform: str,
    page_summary: str,
    canonical_f_refs_block: str,
    phrasing_seeds_block: str = "",
) -> str:
    """Render the synthesizer dispatch prompt with per-engagement substitutions.

    The lead pipes the result into an Agent dispatch (model='opus',
    foreground). When phrasing_seeds_block is empty, the synthesizer runs in
    single-shot mode (writes both audit documents from one author voice).
    When non-empty (degraded-mode dispatch), the synthesizer is told to use
    the seeds verbatim for scope='page' findings.

    canonical_f_refs_block is a markdown-formatted manifest of the post-dedup
    canonical f_refs the synthesizer must use (NOT per-device cluster emission
    local indexes). Build via build_canonical_f_refs_block() from the lead's
    Layer-2 finalized findings.
    """
    template = load_synthesizer_template_body()

    cluster_block = (
        "\n".join(f"- `{p}`" for p in cluster_emission_paths)
        if cluster_emission_paths
        else "  (no cluster emissions provided)"
    )
    desktop_screenshot_block = (
        "\n".join(f"  - `{p}`" for p in desktop_screenshot_paths)
        if desktop_screenshot_paths
        else "  (no desktop screenshots provided)"
    )
    mobile_screenshot_block = (
        "\n".join(f"  - `{p}`" for p in mobile_screenshot_paths)
        if mobile_screenshot_paths
        else "  (no mobile screenshots provided)"
    )

    substitutions = {
        "{{engagement_id}}": engagement_id,
        "{{cluster_emission_paths}}": cluster_block,
        "{{ethics_findings_path}}": ethics_findings_path,
        "{{desktop_baton_path}}": desktop_baton_path,
        "{{mobile_baton_path}}": mobile_baton_path,
        "{{desktop_screenshot_paths}}": desktop_screenshot_block,
        "{{mobile_screenshot_paths}}": mobile_screenshot_block,
        "{{desktop_viewport}}": desktop_viewport,
        "{{mobile_viewport}}": mobile_viewport,
        "{{page_type}}": page_type,
        "{{platform}}": platform,
        "{{page_summary}}": page_summary,
        "{{phrasing_seeds_block}}": phrasing_seeds_block,
        "{{canonical_f_refs_manifest}}": canonical_f_refs_block,
    }

    rendered = template
    for needle, replacement in substitutions.items():
        rendered = rendered.replace(needle, replacement)

    leftover = re.findall(r"\{\{[a-zA-Z_][a-zA-Z_0-9]*\}\}", rendered)
    if leftover:
        raise ValueError(f"Unresolved synthesizer template placeholders: {sorted(set(leftover))}")

    return rendered


# ---------------------------------------------------------------------------
# validate mode — schema + business rules
# ---------------------------------------------------------------------------


def _load_schemas() -> tuple[Any, Any]:
    """Load and compile the validators with a referencing.Registry.

    Returns (validator, finding_schema_dict). Lazy-imports jsonschema +
    referencing so prepare mode runs without the dep installed.
    """
    try:
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
        from referencing.jsonschema import DRAFT202012
    except ImportError as e:
        raise ImportError(
            "jsonschema and referencing are required for validate mode.\n"
            "Install: pip install -r requirements.txt"
        ) from e

    finding_path = REPO_ROOT / "schema" / "finding-v1.json"
    cluster_path = REPO_ROOT / "schema" / "cluster-emission-v1.json"
    finding_schema = json.loads(finding_path.read_text(encoding="utf-8"))
    cluster_schema = json.loads(cluster_path.read_text(encoding="utf-8"))

    finding_resource = Resource.from_contents(finding_schema, default_specification=DRAFT202012)
    cluster_resource = Resource.from_contents(cluster_schema, default_specification=DRAFT202012)
    registry = Registry().with_resources(
        [
            ("https://ecp.local/schema/finding-v1.json", finding_resource),
            ("https://ecp.local/schema/cluster-emission-v1.json", cluster_resource),
        ]
    )
    Draft202012Validator.check_schema(cluster_schema)
    validator = Draft202012Validator(
        cluster_schema,
        registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    return validator, finding_schema


def _run_business_rules(
    emission: dict[str, Any],
    baton: dict[str, Any] | None,
    cluster_vocab: set[str] | None,
    target_band: FindingBand | None,
    *,
    desktop_baton: dict[str, Any] | None = None,
    mobile_baton: dict[str, Any] | None = None,
    anchor_candidates_sidecar: dict[str, Any] | None = None,
) -> list[BusinessRuleViolation]:
    """Run the centralized business-rule validator (assembly.business_rules).

    Phase L: passes cluster_vocab + target_band so the new determinism rules
    fire alongside the original 3 structural-integrity rules.

    Phase M (2026-05-01): also passes desktop_baton + mobile_baton through so
    Phase M's ``_check_element_text_match`` can read full element metadata
    (text_content, accessible_name, role, tag) from the actual loaded baton.
    Earlier callers built an e_index-only surrogate which made the new lint
    false-fail every finding with non-empty ``element.text_content`` because
    the surrogate had empty text fields. Closes Codex P1 follow-up
    (validator drops baton fields before Phase M).

    Phase 4b (2026-05-18): passes anchor_candidates_sidecar through so the
    registry-membership rule fires. Without this kwarg the Phase 4b
    mandatory-candidate contract is direct-unit-test enforced only; the
    real specialist validation CLI silently lets out-of-registry baton_index
    refs through. Closes Codex 2026-05-18 review of 4b30742.
    """
    return _br_validate_business_rules(
        emission,
        baton=baton,
        desktop_baton=desktop_baton,
        mobile_baton=mobile_baton,
        cluster_vocab=cluster_vocab,
        target_band=target_band,
        anchor_candidates_sidecar=anchor_candidates_sidecar,
    )


def validate_synthesizer_emission_file(
    *,
    emission_path: Path,
    finalized_findings_path: Path | None,
    write_retry_prompt: Path | None,
) -> int:
    """Validate a synthesizer-emission-v1.json against schema + allowlist.

    The allowlist is loaded from ``finalized_findings_path`` — a JSON file the
    Layer-2 pipeline writes containing the JSON-derived ``valid_refs`` (every
    real ``"{cluster} F-{NN}"`` for this engagement). When omitted, the
    schema check still runs but the allowlist check is skipped (useful for
    standalone schema validation during prompt iteration).
    """
    if not emission_path.is_file():
        print(f"emission file not found: {emission_path}", file=sys.stderr)
        return 3

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from assembly.synthesizer_parser import (
        SynthesizerValidationError,
        build_v2_retry_prompt,
        validate_synthesizer_emission_payload,
    )

    try:
        payload = json.loads(emission_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"emission is not valid JSON: {e}", file=sys.stderr)
        return 1

    valid_refs: set[str] = set()
    if finalized_findings_path is not None:
        if not finalized_findings_path.is_file():
            print(f"finalized findings file not found: {finalized_findings_path}", file=sys.stderr)
            return 3
        ff = json.loads(finalized_findings_path.read_text(encoding="utf-8"))
        for ref in ff.get("valid_refs") or []:
            valid_refs.add(ref)
        if not valid_refs:
            print(
                f"warning: {finalized_findings_path} contained no valid_refs;"
                f" allowlist check will reject every f_ref",
                file=sys.stderr,
            )

    try:
        validate_synthesizer_emission_payload(payload, valid_refs, source_path=str(emission_path))
    except SynthesizerValidationError as err:
        print(
            f"FAIL - {emission_path.name} synthesizer-emission validation: "
            f"{len(err.schema_errors)} schema error(s), "
            f"{len(err.hallucinated_refs)} hallucinated f_ref(s)",
            file=sys.stderr,
        )
        for path, msg in err.schema_errors[:10]:
            print(f"  SCHEMA:   {path}: {msg}", file=sys.stderr)
        for location, ref in err.hallucinated_refs[:10]:
            print(f"  RULE:     {location}: hallucinated {ref!r}", file=sys.stderr)
        if write_retry_prompt is not None:
            retry = build_v2_retry_prompt(
                str(emission_path), err, valid_refs=valid_refs or None
            )
            atomic_write_text(write_retry_prompt, retry)
            print(f"\nRetry prompt written to {write_retry_prompt}", file=sys.stderr)
        return 1

    print(f"OK - {emission_path.name} validates against synthesizer-emission-v1.json")
    print(f"  engagement_id: {payload.get('engagement_id')}")
    print(f"  status: {payload.get('status')}")
    print(f"  dispatch_shape: {payload.get('dispatch_shape')}")
    print(f"  priority_path: {len(payload.get('priority_path') or [])} stories")
    print(
        f"  scope_page_synchronized_refs: "
        f"{len(payload.get('scope_page_synchronized_refs') or [])}"
    )
    if not valid_refs:
        print("  (allowlist check skipped - no --finalized-findings provided)")
    return 0


def run_drift_check(
    *,
    desktop_md_path: Path,
    mobile_md_path: Path,
    synthesizer_emission_path: Path,
) -> int:
    """Run the Phase F.3 cross-device synchronization assertion.

    Reads the synthesizer-emission to get the scope_page_synchronized_refs
    list, then compares the rendered prose for each ref between desktop and
    mobile audit documents. Reports max Levenshtein ratio and exits non-zero
    if any ratio exceeds SYNCHRONIZATION_THRESHOLD.
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from assembly.synth_input import (
        SYNCHRONIZATION_THRESHOLD,
        assert_synchronization_invariant,
    )

    for p in (desktop_md_path, mobile_md_path, synthesizer_emission_path):
        if not p.is_file():
            print(f"file not found: {p}", file=sys.stderr)
            return 3

    desktop_md = desktop_md_path.read_text(encoding="utf-8")
    mobile_md = mobile_md_path.read_text(encoding="utf-8")
    emission = json.loads(synthesizer_emission_path.read_text(encoding="utf-8"))
    refs = emission.get("scope_page_synchronized_refs") or []

    report = assert_synchronization_invariant(desktop_md, mobile_md, refs)
    print(f"scope_page_synchronized_refs: {len(refs)}")
    print(f"threshold: {report.threshold}")
    print(f"max_ratio: {report.max_ratio:.4f}")
    print(f"missing: {len(report.missing)}")
    if report.missing:
        for ref in report.missing[:5]:
            print(f"  MISSING: {ref}", file=sys.stderr)
    for f_ref, obs_r, rec_r, why_r in report.per_finding[:20]:
        marker = " " if max(obs_r, rec_r, why_r) <= report.threshold else "!"
        print(f"  {marker} {f_ref}: obs={obs_r:.4f} rec={rec_r:.4f} why={why_r:.4f}")
    if report.ok:
        print("OK - cross-device synchronization invariant holds.")
        return 0
    print(
        f"FAIL - synthesis drift exceeds threshold ({report.max_ratio:.4f} > "
        f"{SYNCHRONIZATION_THRESHOLD}).",
        file=sys.stderr,
    )
    return 1


def _auto_discover_anchor_candidates_path(emission_path: Path) -> Path | None:
    """Phase 4b (2026-05-18) — locate the anchor-candidates sidecar by
    convention so callers don't have to pass --anchor-candidates-path
    every time the file lives next to the emission.

    Rules:
    - ``cluster-*-{device}.json`` → ``<dir>/anchor-candidates-{device}.json``
    - ``ethics-findings.json``    → ``<dir>/anchor-candidates-page.json``
      with fallback to ``<dir>/anchor-candidates-desktop.json``
    - Anything else: return None (no auto-discovery)

    Returns the Path if a sidecar exists on disk, else None.
    """
    parent = emission_path.parent
    name = emission_path.name
    if name == "ethics-findings.json":
        page = parent / "anchor-candidates-page.json"
        if page.exists():
            return page
        desktop = parent / "anchor-candidates-desktop.json"
        if desktop.exists():
            return desktop
        return None
    for dev in ("desktop", "mobile", "laptop"):
        if f"-{dev}.json" in name:
            candidate = parent / f"anchor-candidates-{dev}.json"
            return candidate if candidate.exists() else None
    return None


def validate_emission(
    *,
    emission_path: Path,
    baton_path: Path | None,
    desktop_baton_path: Path | None,
    mobile_baton_path: Path | None,
    expected_cluster: str | None,
    expected_engagement_id: str | None,
    write_retry_prompt: Path | None,
    anchor_candidates_path: Path | None = None,
) -> int:
    if not emission_path.is_file():
        print(f"emission file not found: {emission_path}", file=sys.stderr)
        return 3
    try:
        emission = json.loads(emission_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"emission is not valid JSON: {e}", file=sys.stderr)
        return 1

    # Phase M (2026-05-01): pass FULL loaded batons through to the validator
    # rather than an e_index-only surrogate. Phase M's element_text_matches_baton
    # rule reads text_content / accessible_name / role / tag from baton entries;
    # the surrogate had empty text fields and false-failed valid findings.
    # Closes Codex P1 follow-up.
    def _load_baton_or_fail(p: Path | None) -> dict | None:
        if p is None:
            return None
        if not p.is_file():
            print(f"baton file not found: {p}", file=sys.stderr)
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    loaded_baton = _load_baton_or_fail(baton_path)
    loaded_desktop = _load_baton_or_fail(desktop_baton_path)
    loaded_mobile = _load_baton_or_fail(mobile_baton_path)

    # If any path was provided but missing on disk, fail fast (preserves the
    # original behavior where a bad path returned exit 3).
    for label, p, loaded in (
        ("baton_path", baton_path, loaded_baton),
        ("desktop_baton_path", desktop_baton_path, loaded_desktop),
        ("mobile_baton_path", mobile_baton_path, loaded_mobile),
    ):
        if p is not None and loaded is None:
            return 3

    # Phase 4b (2026-05-18) + Phase 4b hardening 2 — load anchor-candidates
    # sidecar via the strict shared loader. "Missing file" → None (legacy
    # skip); "present but broken" → SidecarLoadError raised, surfaced as
    # exit 1 with a clear message. Codex 2026-05-18 review caught the
    # earlier fail-open behavior where an auto-discovered broken sidecar
    # silently disabled the registry rule.
    from assembly.anchor_candidates import (
        SidecarLoadError, load_anchor_candidates_sidecar_strict,
    )
    loaded_sidecar: dict[str, Any] | None = None
    sidecar_source: Path | None = anchor_candidates_path
    if anchor_candidates_path is not None:
        if not anchor_candidates_path.is_file():
            print(
                f"anchor-candidates sidecar not found: {anchor_candidates_path}",
                file=sys.stderr,
            )
            return 3
        try:
            loaded_sidecar = load_anchor_candidates_sidecar_strict(anchor_candidates_path)
        except SidecarLoadError as e:
            print(str(e), file=sys.stderr)
            return 1
    else:
        auto = _auto_discover_anchor_candidates_path(emission_path)
        if auto is not None:
            try:
                loaded_sidecar = load_anchor_candidates_sidecar_strict(auto)
                sidecar_source = auto
            except SidecarLoadError as e:
                # Auto-discovered AND present-but-broken — must NOT silently
                # fall through to None (that disables the registry rule
                # while pretending we're in legacy mode). Fail loud.
                print(str(e), file=sys.stderr)
                return 1

    # Single 'baton' kwarg covers the legacy single-baton case (cluster specialist
    # emissions). desktop/mobile kwargs cover ethics emissions which reference
    # both devices. The validator's internal _e_indexes() unions across all three.
    baton: dict[str, Any] | None = loaded_baton

    # Phase L: load cluster vocab + target band from cluster contract.
    # Cluster comes from emission (for self-validation) or expected_cluster.
    cluster_vocab: set[str] | None = None
    target_band: FindingBand | None = None
    cluster_for_params = emission.get("cluster") or expected_cluster
    if cluster_for_params and cluster_for_params in VALID_CLUSTERS:
        try:
            params = load_specialist_params(cluster_for_params)
            vocab_list = params.get("surface_vocabulary") or []
            if vocab_list:
                cluster_vocab = set(vocab_list)
            target_band = params.get("target_band")
        except (FileNotFoundError, ValueError):
            # Cluster contract missing or malformed — skip Phase L checks
            pass

    validator, _ = _load_schemas()
    schema_errors_raw = sorted(validator.iter_errors(emission), key=lambda e: list(e.absolute_path))
    schema_errors = [
        f"path={list(e.absolute_path)} message={e.message}" for e in schema_errors_raw
    ]

    # Phase L: centralized business rules with vocab + band kwargs.
    # Phase M (2026-05-01): also pass desktop + mobile baton kwargs through so
    # ethics-emission validation has access to both devices' full element data.
    try:
        violations = _run_business_rules(
            emission,
            baton,
            cluster_vocab,
            target_band,
            desktop_baton=loaded_desktop,
            mobile_baton=loaded_mobile,
            anchor_candidates_sidecar=loaded_sidecar,
        )
        # Phase 4b (2026-05-18): prefix each violation string with [rule_name]
        # so stderr is greppable for specific rule discriminators
        # (e.g., "baton_index_in_candidate_registry"). Closes Codex
        # 2026-05-18 review of 4b30742 — Codex's acceptance test asserts
        # the rule name appears in stderr.
        business_errors = [f"[{v.rule}] {v}" for v in violations]
    except ValueError as e:
        # v1 schema_version assertion — this should never fire on real v2
        # emissions, but if it does we surface it as an error rather than crash.
        business_errors = [f"v1-emission-routed-to-v2-validator: {e}"]
        violations = []

    # Identity checks (cheap, surface mismatches before the bulk schema output)
    identity_errors: list[str] = []
    if expected_cluster and emission.get("cluster") != expected_cluster:
        identity_errors.append(
            f"emission.cluster={emission.get('cluster')!r} != expected {expected_cluster!r}"
        )
    if expected_engagement_id and emission.get("engagement_id") != expected_engagement_id:
        identity_errors.append(
            f"emission.engagement_id={emission.get('engagement_id')!r} != expected"
            f" {expected_engagement_id!r}"
        )

    all_errors = identity_errors + schema_errors + business_errors
    cluster_for_prompt = emission.get("cluster") or expected_cluster or "unknown"
    device_for_prompt = emission.get("device") or "unknown"

    if not all_errors:
        print(f"OK - {emission_path.name} validates against cluster-emission-v1.json")
        print(f"  cluster: {emission.get('cluster')}")
        print(f"  device: {emission.get('device')}")
        print(f"  status: {emission.get('status')}")
        print(f"  findings: {len(emission.get('findings', []))}")
        return 0

    print(f"FAIL - {emission_path.name} has {len(all_errors)} validation error(s):", file=sys.stderr)
    for err in identity_errors:
        print(f"  IDENTITY: {err}", file=sys.stderr)
    for err in schema_errors:
        print(f"  SCHEMA:   {err}", file=sys.stderr)
    for err in business_errors:
        print(f"  RULE:     {err}", file=sys.stderr)

    if write_retry_prompt is not None:
        # Phase L: use centralized build_retry_prompt for category-agnostic preamble
        # + deterministic violation sort. Schema errors are still surfaced via the
        # SCHEMA: prefix lines printed above; the retry prompt focuses on
        # business-rule violations (which the specialist can act on directly).
        retry = _br_build_retry_prompt(cluster_for_prompt, device_for_prompt, violations)
        if schema_errors:
            # Prepend a brief schema-error block since centralized build_retry_prompt
            # only handles BusinessRuleViolation objects.
            schema_block = "Schema errors (fix these too):\n" + "\n".join(
                f"- {e}" for e in schema_errors[:8]
            )
            if len(schema_errors) > 8:
                schema_block += f"\n- ... and {len(schema_errors) - 8} more"
            retry = f"{schema_block}\n\n{retry}"
        atomic_write_text(write_retry_prompt, retry)
        print(f"\nRetry prompt written to {write_retry_prompt}", file=sys.stderr)

    return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="test-specialist.py",
        description=(
            "Split-mode harness for v2 specialist dispatch."
            " 'prepare' renders the dispatch prompt; 'validate' checks an emission."
        ),
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    p_prepare = sub.add_parser("prepare", help="Render the dispatch prompt to stdout.")
    p_prepare.add_argument("--cluster", required=True, choices=sorted(VALID_CLUSTERS))
    p_prepare.add_argument("--device", required=True, choices=sorted(VALID_DEVICES))
    p_prepare.add_argument("--engagement-id", required=True)
    p_prepare.add_argument("--cluster-context-path", required=True)
    p_prepare.add_argument("--baton-path", required=True)
    p_prepare.add_argument("--viewport-width", type=int, required=True)
    p_prepare.add_argument("--viewport-height", type=int, required=True)
    p_prepare.add_argument("--dpr", type=float, default=1.0)
    p_prepare.add_argument("--page-type", default="product-page")
    p_prepare.add_argument("--platform", default="unknown")
    p_prepare.add_argument(
        "--screenshot",
        action="append",
        default=[],
        help="Path to a section screenshot. Pass --screenshot once per file.",
    )
    p_prepare.add_argument(
        "--out",
        type=Path,
        help="If set, write the rendered prompt to this path atomically (else stdout).",
    )

    p_validate = sub.add_parser("validate", help="Validate a specialist or synthesizer emission.")
    p_validate.add_argument("--emission-path", type=Path, required=True)
    p_validate.add_argument(
        "--schema",
        choices=["cluster-emission", "synthesizer-emission"],
        default="cluster-emission",
        help=(
            "Which emission schema to validate against. 'cluster-emission'"
            " (default) checks specialist + ethics emissions; 'synthesizer-emission'"
            " checks the Layer-3 synthesizer JSON (Phase F.4)."
        ),
    )
    p_validate.add_argument(
        "--baton-path",
        type=Path,
        help=(
            "Path to baton.json for baton_index resolution checks."
            " For cluster specialists, this is the single device baton."
            " If omitted, baton-index business rule is skipped."
            " Ignored when --schema synthesizer-emission."
        ),
    )
    p_validate.add_argument(
        "--desktop-baton-path",
        type=Path,
        help=(
            "Path to desktop baton.json. Use with ethics emissions where"
            " findings can reference either device's baton."
        ),
    )
    p_validate.add_argument(
        "--mobile-baton-path",
        type=Path,
        help=(
            "Path to mobile baton.json. Use with ethics emissions alongside"
            " --desktop-baton-path."
        ),
    )
    p_validate.add_argument(
        "--anchor-candidates-path",
        type=Path,
        help=(
            "Phase 4b (2026-05-18): path to anchor-candidates-{device}.json"
            " for the registry-membership rule. When omitted, the script"
            " auto-discovers a sibling sidecar by emission filename"
            " convention (cluster-*-desktop.json -> anchor-candidates-desktop.json,"
            " ethics-findings.json -> anchor-candidates-page.json falling"
            " back to anchor-candidates-desktop.json). When no sidecar is"
            " found, the registry check is silently skipped (legacy"
            " preservation). If the provided path is missing or malformed,"
            " validation fails fast."
        ),
    )
    p_validate.add_argument(
        "--finalized-findings",
        type=Path,
        help=(
            "Synthesizer-only. JSON file containing 'valid_refs' from the"
            " Layer-2 finalized findings. When omitted with"
            " --schema synthesizer-emission, allowlist check is skipped."
        ),
    )
    p_validate.add_argument("--expect-cluster", help="Optional: assert emission.cluster matches.")
    p_validate.add_argument(
        "--expect-engagement-id", help="Optional: assert emission.engagement_id matches."
    )
    p_validate.add_argument(
        "--write-retry-prompt",
        type=Path,
        help="If set and validation fails, write the retry prompt to this path.",
    )

    p_prep_synth = sub.add_parser(
        "prepare-synthesizer",
        help="Render the synthesizer dispatch prompt (Phase F.2).",
    )
    p_prep_synth.add_argument("--engagement-id", required=True)
    p_prep_synth.add_argument(
        "--cluster-emission",
        action="append",
        default=[],
        required=True,
        help="Path to a cluster-emission-v1.json. Pass once per file (10 specialists per device).",
    )
    p_prep_synth.add_argument("--ethics-findings-path", required=True)
    p_prep_synth.add_argument("--desktop-baton-path", required=True)
    p_prep_synth.add_argument("--mobile-baton-path", required=True)
    p_prep_synth.add_argument(
        "--desktop-screenshot",
        action="append",
        default=[],
        help="Desktop section screenshot. Pass once per file.",
    )
    p_prep_synth.add_argument(
        "--mobile-screenshot",
        action="append",
        default=[],
        help="Mobile section screenshot. Pass once per file.",
    )
    p_prep_synth.add_argument("--desktop-viewport", default="1920x1080")
    p_prep_synth.add_argument("--mobile-viewport", default="390x844")
    p_prep_synth.add_argument("--page-type", default="product-page")
    p_prep_synth.add_argument("--platform", default="unknown")
    p_prep_synth.add_argument(
        "--page-summary",
        default="(no page summary supplied)",
        help="Short prose summary of the page; the synthesizer uses it for executive-summary framing.",
    )
    p_prep_synth.add_argument(
        "--phrasing-seeds-path",
        type=Path,
        help="Optional. Path to a markdown file containing phrasing seeds for degraded-mode dispatch.",
    )
    p_prep_synth.add_argument(
        "--canonical-f-refs-path",
        type=Path,
        required=True,
        help="Required. Path to a JSON file with the canonical post-dedup f_refs the synthesizer must use. "
        "Build via the lead's Layer-2 finalize step. Format: "
        '{"valid_refs": ["pricing F-01", ...], "by_canonical_ref": {"pricing F-01": {"title": "...", '
        '"scope": "page", "devices": ["desktop", "mobile"], "cluster_local_index_per_device": {...}}}}',
    )
    p_prep_synth.add_argument(
        "--out",
        type=Path,
        help="If set, write the rendered prompt to this path atomically (else stdout).",
    )

    p_drift = sub.add_parser(
        "drift-check",
        help="Run the Phase F.3 cross-device synchronization assertion.",
    )
    p_drift.add_argument("--desktop-md", type=Path, required=True)
    p_drift.add_argument("--mobile-md", type=Path, required=True)
    p_drift.add_argument("--synthesizer-emission", type=Path, required=True)

    args = parser.parse_args(argv)

    if args.mode == "prepare":
        rendered = render_prompt(
            cluster=args.cluster,
            device=args.device,
            engagement_id=args.engagement_id,
            cluster_context_path=args.cluster_context_path,
            baton_path=args.baton_path,
            viewport_width=args.viewport_width,
            viewport_height=args.viewport_height,
            dpr=args.dpr,
            page_type=args.page_type,
            platform=args.platform,
            screenshot_paths=args.screenshot,
        )
        if args.out:
            atomic_write_text(args.out, rendered)
            print(f"prompt written to {args.out}", file=sys.stderr)
        else:
            sys.stdout.write(rendered)
            if not rendered.endswith("\n"):
                sys.stdout.write("\n")
        return 0

    if args.mode == "validate":
        if args.schema == "synthesizer-emission":
            return validate_synthesizer_emission_file(
                emission_path=args.emission_path,
                finalized_findings_path=args.finalized_findings,
                write_retry_prompt=args.write_retry_prompt,
            )
        return validate_emission(
            emission_path=args.emission_path,
            baton_path=args.baton_path,
            desktop_baton_path=args.desktop_baton_path,
            mobile_baton_path=args.mobile_baton_path,
            expected_cluster=args.expect_cluster,
            expected_engagement_id=args.expect_engagement_id,
            write_retry_prompt=args.write_retry_prompt,
            anchor_candidates_path=args.anchor_candidates_path,
        )

    if args.mode == "prepare-synthesizer":
        seeds_block = ""
        if args.phrasing_seeds_path is not None:
            if not args.phrasing_seeds_path.is_file():
                print(f"phrasing seeds file not found: {args.phrasing_seeds_path}", file=sys.stderr)
                return 3
            seeds_block = args.phrasing_seeds_path.read_text(encoding="utf-8")
        if not args.canonical_f_refs_path.is_file():
            print(f"canonical f_refs file not found: {args.canonical_f_refs_path}", file=sys.stderr)
            return 3
        canonical_data = json.loads(args.canonical_f_refs_path.read_text(encoding="utf-8"))
        canonical_block = build_canonical_f_refs_block(canonical_data)
        rendered = render_synthesizer_prompt(
            engagement_id=args.engagement_id,
            cluster_emission_paths=args.cluster_emission,
            ethics_findings_path=args.ethics_findings_path,
            desktop_baton_path=args.desktop_baton_path,
            mobile_baton_path=args.mobile_baton_path,
            desktop_screenshot_paths=args.desktop_screenshot,
            mobile_screenshot_paths=args.mobile_screenshot,
            desktop_viewport=args.desktop_viewport,
            mobile_viewport=args.mobile_viewport,
            page_type=args.page_type,
            platform=args.platform,
            page_summary=args.page_summary,
            phrasing_seeds_block=seeds_block,
            canonical_f_refs_block=canonical_block,
        )
        if args.out:
            atomic_write_text(args.out, rendered)
            print(f"prompt written to {args.out}", file=sys.stderr)
        else:
            sys.stdout.write(rendered)
            if not rendered.endswith("\n"):
                sys.stdout.write("\n")
        return 0

    if args.mode == "drift-check":
        return run_drift_check(
            desktop_md_path=args.desktop_md,
            mobile_md_path=args.mobile_md,
            synthesizer_emission_path=args.synthesizer_emission,
        )

    parser.error(f"unknown mode {args.mode!r}")
    return 2  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
