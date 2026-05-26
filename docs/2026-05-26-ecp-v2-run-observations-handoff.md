# Handoff — Observations from a live ECP v2 audit run (2026-05-26)

**Context:** Full `/ecp:audit` run on `https://www.awdmods.com/` (Shopify homepage), dual-device (mobile + desktop), comprehensive scope (6 clusters → 12 specialists + ethics + synthesizer + dual render). Engagement: `docs/ecp/2026-05-26-446a4b47/`. The audit completed and shipped all deliverables, but the lead (Claude) had to work around several real issues to get there. Everything below was **observed during this run**, not inferred from reading code in isolation. Verify line numbers against current `HEAD` before acting — they're from the 2026-05-26 tree.

Severity key: **P0** blocks/forces-rework on a normal run · **P1** correctness/robustness · **P2** quality/polish.

---

## P0-1 — `lead_prep.py build-canonical-frefs` is inconsistent with the renderer (the big one)

**File:** `scripts/lead_prep.py` → `build_canonical_frefs()` (~lines 159–260), vs `scripts/report/v2_loader.py` (the `_build_canonical_view` path, ~lines 395–438).

**What happens:** The canonical f_refs manifest is the allowlist the synthesizer is told to cite from. `build_canonical_frefs()` builds it by iterating **cluster emissions only** and calling `FinalizedFindings.build(findings_assembly, clusters_used)` directly. The renderer builds its finding universe differently: it loads cluster emissions **plus `ethics-findings.json`**, then runs `deduplicate_v2(...).all_actionable()` **before** `FinalizedFindings.build(...)`.

Because `display_index` is content-hash-derived AND cross-device dedup collapses duplicate findings, the two paths produce **different allowlists**:
- `build-canonical-frefs` on this run: **70 refs, 0 ethics**.
- renderer truth: **76 refs** (68 cluster after dedup + 8 ethics).

**Consequence:** The synthesizer faithfully used the (wrong) manifest and emitted 4 refs the renderer would reject:
- `ethics F-01` → should be `ethics F-90` (ethics findings get hash-derived indices too; they were entirely absent from the manifest so the model invented `F-01`).
- `category-navigation F-53` → `F-52`, `trust-credibility F-65` → `F-12` (collapsed by dedup).
- `pricing F-55` → merged into `pricing F-56` (cross-device dedup of the mobile "From Price…" finding into the desktop "Open-Ended From Prices…" finding).

The lead caught this only by rebuilding the allowlist from the renderer's exact path and diffing. **A lead following the SKILL router literally would ship a synthesizer emission with broken/hallucinated f_refs**, and the visual report would drop those findings' hotspots.

**Fix:** Make `build_canonical_frefs()` mirror `v2_loader`'s input universe — load `ethics-findings.json` into the finding list and run `deduplicate_v2(...).all_actionable()` before `FinalizedFindings.build()`. The v2_loader comment at ~line 432 already asserts the two "share the same input universe"; they don't. Add a test that asserts `build-canonical-frefs` output == the renderer's finalized ref set for a dual-device golden engagement.

---

## P0-2 — SKILL router documents the v1 pipeline for v2 work

**File:** `skills/audit/SKILL.md` → "Validation And Recovery" and "Artifact Contract" sections.

The router tells the lead to run, before assembly:
```
python scripts/validate-cluster-files.py --engagement docs/ecp/{id}
python scripts/assemble-audit.py --engagement docs/ecp/{id} --device {device}
```
Both are **v1 markdown-path tools**. On a v2 engagement (JSON emissions):
- `validate-cluster-files.py` prints `warning: no cluster-*-*.md files` and validates nothing.
- `prep_synth_input.py` (the script that actually feeds the synthesizer) **crashes** with `FileNotFoundError: Missing 6 cluster file(s) … cluster-visual-cta-desktop.md …` because it calls `parser.load_all_cluster_files` which expects `.md`, not the v2 `.json` emissions.
- `assemble-audit.py` is the v1 assembler; v2 has the synthesizer write `audit-{device}.md` directly, so it isn't part of the v2 path at all.

**The actual v2 path the lead had to discover by reading code:** `test-specialist.py validate` (schema + business rules per emission) → `lead_prep.py build-canonical-frefs` → `synth_input.trim_baton_file` (per device) → synthesizer dispatch → `generate-report.py --v2`. None of that is in the router.

**Fix:** Add an explicit "v2 pipeline" subsection to the router (or a `workflows/assemble-v2.md`) listing the real commands and order, and either (a) make `validate-cluster-files.py` / `prep_synth_input.py` v2-aware (detect `.json` emissions / `synthesizer-emission` presence) or (b) clearly mark them v1-only with a pointer to the v2 equivalents.

---

## P1-1 — Non-ASCII in canary summaries crashes on Windows consoles

**File:** `scripts/assembly/canary_checks.py` (summary strings contain `→`, e.g. "… vs threshold 0.80 → FAIL").

Printing those summaries on a default Windows console (cp1252) raises `UnicodeEncodeError: 'charmap' codec can't encode character '→'`. The lead's first `run_all_canaries` invocation aborted mid-loop on this and had to be re-run with `PYTHONIOENCODING=utf-8`. The user runs on Windows 11 — this will bite any Windows operator.

**Fix:** Use ASCII (`->`) in canary/summary strings, or have CLI entrypoints call `sys.stdout.reconfigure(encoding="utf-8")` at startup. Worth a repo-wide sweep for non-ASCII in `print()`/summary strings given the Windows audience.

---

## P1-2 — Acquirer emits a baton element with negative rect coord; schema rejects it

**Files:** `workflows/acquire.md` (Step 3b element extraction) + `schema/baton-v1.json` (`elements[].rect.{x,y}` `minimum: 0`).

The desktop baton had `elements[14].rect.x = -13.0` (a partially off-canvas element from `getBoundingClientRect`). This fails schema validation (`-13.0 is less than the minimum of 0`). The lead clamped negatives to 0 by hand to proceed.

**Fix:** Clamp negative `x/y` to 0 in the acquirer before writing the baton (one line in the e_index assignment step), **or** relax the schema to allow small negatives for partially-off-canvas elements. Clamping at the source is cleaner.

---

## P1-3 — High emission-bounce rate (5 of 13 agent emissions needed a retry)

Across this run: 4 of 12 cluster specialists bounced once each, the ethics subagent bounced once (5 errors at once), and the synthesizer bounced once (the P0-1 remap). All recovered on the single retry the contract allows, so output quality was fine — but the bounce surface is worth tightening:

- **Anchor-candidate registry friction (2 specialists):** cited a real baton `eN` that wasn't in `anchor-candidates-{device}.json`. The ranker (`scripts/assembly/anchor_candidates.py`) is conservative; consider widening candidate role coverage or making the specialist prompt steer harder to `candidate_id` citation so the common case doesn't trip `check_baton_index_in_candidate_registry`.
- **`proposed_anchor.reason` length (1 specialist):** exceeded the 200-char cap. The cap isn't surfaced near where the model writes the field in `contracts/specialist-prompt-v2.md` — add the explicit "≤200 chars" inline at the `reason` field definition.
- **Ethics CLEAR `effort` + telemetry shape (ethics):** the model emitted a path-form `telemetry.reference_files_read` and missed `proposed_anchor` on an absent finding. These are recurring ethics-emission shape traps (the contract even documents the awdmods 2026-05-18 CLEAR-`change_type` patch). A tiny ethics emission validator-with-autofix, or a fuller one-shot example covering the absent-finding + telemetry shape, would cut this.

---

## P1-4 — Ethics subagent cited the wrong jurisdiction

The ethics subagent flagged the privacy-policy-link issue (legit — points to the `*.myshopify.com` staging domain) but cited **GDPR Art 13** for a page it had itself determined was **US-targeted, no EU hreflang**. The lead had it switch to **CCPA (Cal. Civ. Code §1798.130/.135)**. The `source_url` was a valid Source Registry URL, so the canary passed — the canary checks *presence* of a non-self-cite URL, not jurisdictional fit.

**Fix:** Add a "match the citation to the page's actual jurisdiction (US → CCPA/FTC; EU → GDPR/DSA, gated on hreflang/locale)" steer to `contracts/ethics-subagent-v2.md`. Relates to prior ethics-gate calibration feedback.

---

## P2-1 — `element_index_match_rate` soft-canary fails on a real run (0.681 < 0.80)

The synthesizer's `**ELEMENT:**` lines sometimes describe the element without the `at eN` suffix, even though the finding carries `baton_index` structurally (hotspots still resolved — 57/57 placed, 0 fallbacks). The contract notes the slingmods baseline (~0.63) and expects the awdmods golden to reach ~1.0 "after fixture refresh," but it's still sub-threshold on a fresh run.

**Fix (deterministic, cheap):** Since `baton_index` is already in the emission, a post-process could inject `at e{baton_index}` into ELEMENT lines that lack it, rather than relying on the model to format it. That would push the rate to ~1.0 without a synthesizer re-dispatch.

## P2-2 — Oversized "exact" hotspot rectangles + proxy overload

`visual_evidence_giant_exact_rectangles` soft-failed (desktop 4/28, mobile 2/14 exact-element markers exceed 85%w/70%h) and `proxy_overload` WARNed (desktop 50%, mobile 74% non-exact). The giant rectangles come from exact anchors on large baton elements (nav/header/section wrappers).

**Fix to consider:** In the marker/renderer logic, auto-demote an exact-element marker to a section/proxy anchor when its baton rect exceeds a size threshold, so a whole-nav element doesn't render as a screen-filling "exact" box.

## P2-3 — Acquirer `--screenshot-quality` is session-global, not per-command

The mobile acquirer captured its first screenshot before learning `--screenshot-quality` applies to the session, so mobile shots shipped larger than the quality-60 target (cosmetic; all valid JPEGs). Worth a one-line note in `workflows/acquire.md` Step 3 that the quality flag must be set on the session before the first capture.

---

## What went well (so the fixes don't regress it)

- **Dispatch discipline held end-to-end:** 12 specialists + ethics + synthesizer all ran as the correct dispatch shape; the lead never authored findings or the Priority Path inline; bounces went back to the owning agent.
- **Hotspot resolution was clean:** 57/57 hotspots placed across both devices with **zero banner/operator fallbacks** — a real improvement over the historical "screenshots not sticky / wrong-element hotspot" class.
- **Cross-device synchronization invariant held** (sync_refs byte-identical in both audits; drift check passed).
- **Ethics calibration was correct** on the hard cases: no false-CRITICALs on shipping disclosure, truthful-low-review social proof, decorative imagery, or touch-target sizing.

---

## Suggested triage order
1. **P0-1** (canonical-fref drift) — highest leverage; recurs on every dual-device v2 run.
2. **P0-2** (router documents v1 for v2) — prevents the next lead from hitting the same crashes.
3. **P1-1** (Windows encoding) — cheap, and the operator is on Windows.
4. **P1-2 / P1-3 / P1-4**, then **P2-***.

Full per-run detail is in `docs/ecp/2026-05-26-446a4b47/lead-reflection.md` and `audit-trace.log`.
