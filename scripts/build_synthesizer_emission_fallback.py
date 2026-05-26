"""Lead-side fallback builder for synthesizer-emission-v1.json.

Used when the Layer-3 synthesizer wrote audit-{device}.md but ran out of
context budget before writing the structured emission. Reconstructs the
emission deterministically from:

- audit-desktop.md + audit-mobile.md (priority_path narratives, finding refs)
- cluster emissions + ethics-findings.json (effort metadata for manifests)
- canonical-f-refs.json (allowlist + scope_page_synchronized_refs basis)

The schema makes humanized_findings OPTIONAL — the renderer's graceful
fallback (Phase G follow-up #1) reads dev-spec prose from the audit
markdowns when humanized_findings is absent. So this builder skips
humanized_findings; the visual report still renders correctly.

Phase J D2 emergency tooling (2026-04-28). Promote to a proper integration
in v2.1 if this pattern recurs.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from assembly.json_parser import parse_emission_file


SEVERITY_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
TIER_RANK = {"Gold": 3, "Silver": 2, "Bronze": 1}


def parse_priority_path(audit_md: str) -> list[dict]:
    """Extract priority_path stories from a `## Top Priorities` section.

    Each story is `### {title}\\n\\n{narrative paragraph}\\n\\n[ref1, ref2, ...]`.
    """
    stories = []
    # Find the ## Top Priorities section
    m = re.search(r"^## Top Priorities\s*$(.*?)^## ", audit_md, re.MULTILINE | re.DOTALL)
    if not m:
        return stories
    body = m.group(1)
    # Each story starts with ### and ends with [refs...]
    for story in re.finditer(
        r"^### (.+?)\s*\n\n(.*?)\n\n\[([^\]]+)\]\s*$",
        body,
        re.MULTILINE | re.DOTALL,
    ):
        title = story.group(1).strip()
        narrative = story.group(2).strip()
        refs_raw = story.group(3)
        f_refs = [r.strip() for r in refs_raw.split(",") if r.strip()]
        stories.append({
            "mode": "bundle",
            "title": title,
            "severity": "HIGH",
            "narrative": narrative,
            "f_refs": f_refs,
        })
    return stories


def _load_anchor_candidates_sidecars(eng_dir: Path) -> dict[str, dict | None]:
    """Phase 4a hardening (2026-05-18) — load anchor-candidates-{device}.json
    sidecars so parse_emission_file can resolve candidate_id-only emissions.
    Closes Codex 2026-05-18 review item 2 on ffeb1a6 (fallback path).

    Phase 4b hardening 2 (2026-05-18) — use the strict shared loader.
    Missing file → None (legacy skip). Present-but-broken → raise
    SidecarLoadError so the fallback caller fails loud instead of
    silently bypassing candidate-id resolution. Codex 2026-05-18 review
    of 64ce7f2.
    """
    from assembly.anchor_candidates import load_anchor_candidates_sidecar_strict
    out: dict[str, dict | None] = {}
    for dev in ("desktop", "mobile", "laptop", "page"):
        out[dev] = load_anchor_candidates_sidecar_strict(
            eng_dir / f"anchor-candidates-{dev}.json"
        )
    return out


def collect_findings(eng_dir: Path) -> list:
    """Read all 21 emissions (20 cluster + 1 ethics).

    Phase 4a hardening: passes anchor-candidates-{device}.json sidecars
    into parse_emission_file so candidate_id-only emissions resolve to
    canonical baton_index. Without this, the synthesizer-emission fallback
    silently rejected any specialist that used Phase 4a candidate_id-only
    syntax.
    """
    sidecars = _load_anchor_candidates_sidecars(eng_dir)
    findings = []
    for p in sorted(eng_dir.glob("cluster-*.json")):
        if p.name.startswith("cluster-context-"):
            continue
        # Pick sidecar by filename suffix (-desktop.json, -mobile.json, etc.)
        sidecar = None
        for dev, sc in sidecars.items():
            if f"-{dev}.json" in p.name and sc is not None:
                sidecar = sc
                break
        result = parse_emission_file(p, anchor_candidates_sidecar=sidecar)
        findings.extend(result.findings)
    eth_path = eng_dir / "ethics-findings.json"
    if eth_path.exists():
        # Ethics emissions use device="page" — pick the page sidecar if present
        eth = parse_emission_file(eth_path, anchor_candidates_sidecar=sidecars.get("page"))
        findings.extend(eth.findings)
    return findings


def derive_quick_wins(findings, valid_refs: set[str]) -> list[str]:
    """Quick wins: effort.change_type IN {copy, css, html-attr} AND
    change_scope IN {single-file, component}."""
    QUICK_TYPES = {"copy", "css", "html-attr"}
    QUICK_SCOPES = {"single-file", "component"}
    out = []
    seen = set()
    for f in findings:
        change_type = getattr(getattr(f, "effort", None), "change_type", None)
        change_scope = getattr(getattr(f, "effort", None), "change_scope", None)
        if change_type in QUICK_TYPES and change_scope in QUICK_SCOPES:
            ref = f"{f.cluster} F-{f.local_index:02d}"
            if ref in valid_refs and ref not in seen:
                seen.add(ref)
                out.append(ref)
    return out


def derive_severity_manifest(findings, valid_refs: set[str]) -> list[str]:
    """Sort findings by (severity desc, evidence_tier desc, confidence desc)."""
    rows = []
    seen = set()
    for f in findings:
        ref = f"{f.cluster} F-{f.local_index:02d}"
        if ref not in valid_refs or ref in seen:
            continue
        seen.add(ref)
        sev = getattr(f, "severity", None) or "?"
        tier = getattr(f, "evidence_tier", None) or "Bronze"
        conf = getattr(f, "confidence", None) or 0.5
        rows.append((SEVERITY_RANK.get(sev, 0), TIER_RANK.get(tier, 0), conf, ref))
    rows.sort(key=lambda r: (-r[0], -r[1], -r[2]))
    return [r[3] for r in rows]


def derive_sync_refs(audit_desktop: str, audit_mobile: str, valid_refs: set[str]) -> list[str]:
    """f_refs whose OBSERVATION + RECOMMENDATION + Why-this-matters paragraphs
    are byte-identical across both device markdowns.
    """
    def extract_per_finding_prose(audit: str) -> dict[str, str]:
        # Find each `#### {f_ref} — {title}` block and extract its prose paragraphs
        out = {}
        # Pattern: `#### {cluster} F-{NN} — {title}\n\n...\n\n#### ` or end of file
        pattern = re.compile(
            r"^#### ([a-z][a-z0-9-]+ F-\d+)\b[^\n]*\n(.*?)(?=^#### |^### |^## |\Z)",
            re.MULTILINE | re.DOTALL,
        )
        for m in pattern.finditer(audit):
            ref = m.group(1)
            body = m.group(2)
            # Extract OBSERVATION / RECOMMENDATION / Why-this-matters bodies
            obs = re.search(r"\*\*OBSERVATION:\*\*\s*(.*?)(?=\n\n\*\*|\Z)", body, re.DOTALL)
            rec = re.search(r"\*\*RECOMMENDATION:\*\*\s*(.*?)(?=\n\n\*\*|\Z)", body, re.DOTALL)
            why = re.search(r"\*\*Why this matters:\*\*\s*(.*?)(?=\n\n\*\*|\n\n▸|\Z)", body, re.DOTALL)
            joined = "|".join([
                (obs.group(1) if obs else "").strip(),
                (rec.group(1) if rec else "").strip(),
                (why.group(1) if why else "").strip(),
            ])
            out[ref] = joined
        return out

    desktop_prose = extract_per_finding_prose(audit_desktop)
    mobile_prose = extract_per_finding_prose(audit_mobile)
    common = set(desktop_prose) & set(mobile_prose)
    sync = []
    for ref in sorted(common):
        if ref not in valid_refs:
            continue
        if desktop_prose[ref] == mobile_prose[ref]:
            sync.append(ref)
    return sync


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engagement-dir", type=Path, required=True)
    args = parser.parse_args()
    eng_dir = args.engagement_dir

    audit_desktop = (eng_dir / "audit-desktop.md").read_text(encoding="utf-8")
    audit_mobile = (eng_dir / "audit-mobile.md").read_text(encoding="utf-8")
    canonical = json.loads((eng_dir / "canonical-f-refs.json").read_text(encoding="utf-8"))
    valid_refs = set(canonical["valid_refs"])

    findings = collect_findings(eng_dir)
    print(f"Collected {len(findings)} findings; allowlist has {len(valid_refs)} refs")

    priority = parse_priority_path(audit_desktop)
    print(f"Parsed {len(priority)} priority_path stories from audit-desktop.md")

    # Filter priority story f_refs to only those in the allowlist
    for s in priority:
        s["f_refs"] = [r for r in s["f_refs"] if r in valid_refs]

    qwins = derive_quick_wins(findings, valid_refs)
    sev_manifest = derive_severity_manifest(findings, valid_refs)
    sync_refs = derive_sync_refs(audit_desktop, audit_mobile, valid_refs)

    print(f"  quick_wins_manifest: {len(qwins)}")
    print(f"  severity_manifest: {len(sev_manifest)}")
    print(f"  scope_page_synchronized_refs: {len(sync_refs)}")

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    emission = {
        "schema_version": 1,
        "engagement_id": eng_dir.name,
        "synthesizer_model": {
            "family": "opus",
            "version": "4.6",
            "context_window": "1M",
        },
        "started_at": "2026-04-28T23:38:00Z",
        "completed_at": now,
        "status": "complete",
        "dispatch_shape": "single",
        "degraded_mode": False,
        "audit_documents": {
            "desktop": "audit-desktop.md",
            "mobile": "audit-mobile.md",
        },
        "priority_path": priority,
        "quick_wins_manifest": qwins,
        "severity_manifest": sev_manifest,
        "scope_page_synchronized_refs": sync_refs,
        "notes": [
            "synthesizer-emission-v1.json reconstructed deterministically by scripts/build_synthesizer_emission_fallback.py — the Layer-3 synthesizer wrote audit-desktop.md + audit-mobile.md but exhausted its context budget before writing this structured emission. priority_path narratives parsed from audit-desktop.md '## Top Priorities' section; manifests derived from cluster emissions; sync_refs computed by byte-identical prose comparison across the two audit markdowns. humanized_findings intentionally omitted (schema-optional; renderer falls back to dev-spec prose per Phase G follow-up #1).",
        ],
    }

    out = eng_dir / "synthesizer-emission-v1.json"
    out.write_text(json.dumps(emission, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        # Phase 4b hardening 2 — present-but-broken sidecar surfaces here
        # as SidecarLoadError. Don't swallow; print + exit non-zero.
        from assembly.anchor_candidates import SidecarLoadError
        if isinstance(e, SidecarLoadError):
            print(f"ERROR: {e}", file=sys.stderr)
            raise SystemExit(1)
        raise
