---
name: ecp:audit
description: >-
  Runs an e-commerce psychology audit of an existing ecommerce page: cited,
  element-anchored findings, a prioritized Priority Path, and an annotated
  visual report. Covers product pages, checkout flows, carts, pricing, landing
  pages, category pages, and SEO using research-backed findings across pricing,
  trust, mobile, content, and visual design.
disable-model-invocation: true
argument-hint: "[url] [--auto] [--deep] [--min-priority critical|high|medium|low] [--platform shopify|nextjs|opencart] [--device mobile|laptop|desktop] [--focus cluster1,cluster2] [--visual] [--no-visual] [--engagement-id id]"
---

# ECP Audit Router

This skill is the runtime router for the ECP audit. It produces cited, element-anchored findings, a prioritized Priority Path, and an annotated visual report, then stops — plan, review, and build are out of scope per `product.md` §2.4. Keep it lean: load the contracts and workflows named below, run the phases in order, enforce the hard gates, and leave historical rationale in `SKILL.notes.md`.

## Priority Key

- P0 Hard gate: blocks output or phase progression when violated.
- P1 Contract: required for product correctness, with an explicit recovery path where available.
- P2 Guidance: preferred behavior that improves quality or consistency.
- P3 Context: history, rationale, migration notes, and examples; see `SKILL.notes.md`.

## P0 Hard Gates

1. P0-01: The lead MUST follow `contracts/lead-discipline.md` before phase work begins.
2. P0-02: URL mode MUST validate the URL and get fetch confirmation unless `--auto` is set.
3. P0-03: Acquisition MUST dispatch acquirer subagent(s) before any manual fallback.
4. P0-04: The lead MUST verify expected acquisition files exist on disk before reading them or proceeding.
5. P0-05: Dual-device runs MUST keep each device's DOM, baton, screenshots, and audit outputs separated.
6. P0-06: Cluster audit work MUST be dispatched to cluster specialists; the lead NEVER audits a failed cluster as fallback.
7. P0-07: Ethics gate MUST execute before synthesis; BLOCK or ADJACENT ethics findings require real source URLs.
8. P0-08: Every cluster + ethics emission MUST pass validation before synthesis — `scripts/test-specialist.py validate --schema cluster-emission` for v2 JSON emissions (`scripts/validate-cluster-files.py` is legacy v1 markdown only).
9. P0-09: Priority Path synthesis MUST use the protocol and subagent path; inline lead-authored stories are FORBIDDEN.
10. P0-10: Structural assertions in `contracts/trace-assertion-canary.md` MUST run before the audit checkpoint; assertion failure BLOCKS phase progression.
11. P0-11: v2 JSON and state writes MUST use atomic write helpers or scripts that own their output.
12. P0-12: Cancellation sentinel checks MUST happen at layer boundaries; when `cancel.flag` is present, no further dispatches happen.

## Runtime Load Order

Read these files at invocation start:

1. `contracts/lead-discipline.md`
2. `contracts/flags.md`
3. `contracts/audit-state-machine.md`
4. `contracts/dispatch-contract.md`
5. `contracts/device-semantics.md`
6. `contracts/meta-schema.md`

Then load phase-specific files only when that phase is reached.

| Phase | Load when needed |
| --- | --- |
| Input and setup | `contracts/url-validation.md`, `contracts/team-lifecycle.md`, `contracts/platform-detection.md`, `contracts/page-detection.md`, `contracts/cluster-routing.md` |
| Acquisition | `workflows/acquire.md`, `contracts/dom-preprocessor.md` |
| Specialist audit | `workflows/audit.md`, `contracts/specialist-prompt-v2.md`, relevant `references/**` files |
| Ethics | `contracts/ethics-subagent-v2.md`, `references/ethics-gate.md` |
| Synthesis | `contracts/synthesizer-v2.md`, `contracts/synthesizer-subagent.md`, `contracts/priority-path-synthesis.md` |
| Assembly and canaries | `contracts/audit-assembly.md`, `contracts/audit-reconciliation.md`, `contracts/trace-assertion-canary.md`, `contracts/progress-comparison.md` |
| Export | `contracts/report-export.md` |

## Mode Selection

`$ARGUMENTS` must contain a **URL** — the only canonical input (`product.md` §2.2):

- URL mode: starts with `http://` or `https://`.

URL is the sole supported audit input. Screenshot-only and codebase/file inputs are frozen (`product.md` §5) and are not accepted here; if `$ARGUMENTS` is not a URL, ask for one per `contracts/lead-discipline.md`.

Allowed pre-flight prompts are limited by `contracts/lead-discipline.md`: URL detection, URL fetch confirmation, device selection, and audit scope selection. `--auto` uses the audit defaults from `contracts/flags.md`.

## Phase Order

Run this sequence:

1. Parse flags and choose mode.
2. Select device(s) per `contracts/device-semantics.md`.
3. Create or resume `docs/ecp/{engagement-id}` and write/update `meta.json`.
4. Create the audit team per `contracts/team-lifecycle.md`.
5. Detect platform, page type, page pattern, and cluster scope.
6. Dispatch acquisition for each requested device.
7. Verify acquisition artifacts on disk.
8. Preprocess DOM per device when DOM exists.
9. Dispatch cluster specialists for each selected cluster and device — **in waves of ≤5 concurrent spawns** (G-fanout cap, 2026-05-27). The 2026-05-27 concurrent-audits batch hit transient server-side rate limits at 8+ concurrent spawns; a comprehensive 10-cluster × 2-device run takes ~4 waves of 5 to land cleanly. Wait for each wave's file-presence signal before launching the next. See `contracts/dispatch-contract.md` §"Why cluster specialists keep teammate status" point 1 for the rationale.
10. Dispatch ethics v2 after specialist emissions are present.
11. Validate every specialist + ethics emission, build the canonical f_refs manifest, and trim each device baton, then dispatch synthesizer v2 (after ethics completes or records partial status).
12. Validate the synthesizer emission, run the cross-device drift gate, and run structural plus substantive canaries (see "Validation, Synthesis, and Rendering").
13. Present the audit checkpoint with export options.
14. Export the audit markdown and the annotated visual report when requested.
15. Update `meta.json`, write `lead-reflection.md`, run `generate-report.py --mark-reflection-complete` to flip `meta.json` `reflection_state` from `draft` to `complete` (G23, 2026-05-28), and clean up the team at completion.

## Dispatch Shape

Default to v2 dispatch:

- Acquirer: `Task` subagent, one per device.
- Cluster specialists: `Agent` teammates in the audit team.
- Ethics: `Task` subagent.
- Synthesizer: `Task` subagent.

All dispatch targets the **inline subagent contracts** via the Agent/Task tools — the acquirer runs `scripts/cursor_bootstrap_url.py` (canonical despite its Cursor-flavored name), specialists use `contracts/specialist-prompt-v2.md`, ethics uses `contracts/ethics-subagent-v2.md`, synthesizer uses `contracts/synthesizer-v2.md`. The lead NEVER delegates to an `ecp-*` agent file. Any `ecp-orchestrator` / `ecp-acquisition` / `ecp-cluster-auditor` / `ecp-reviewer` / `ecp-synthesizer` agent that the Agent tool's type list may surface is a **frozen Cursor archive** (product.md §5/§8, now relocated to `archive/cursor-agents/`) and must not be selected as a delegation target — the "orchestrator" role is just this audit lead under a Cursor-era name.

Record dispatch counters in `audit-trace.log` using `contracts/trace-assertion-canary.md`. Legacy v1 counter aliases may be accepted only where that contract explicitly says they are accepted.

## Artifact Contract

Write audit artifacts inside `docs/ecp/{engagement-id}/`:

- `meta.json`
- `audit-trace.log`
- acquisition artifacts: `baton.json` / `dom.html` for non-mobile, `baton-mobile.json` / `dom-mobile.html` for mobile
- cluster emissions: `cluster-{cluster}-{device}.md` or v2 JSON emissions as specified by the loaded workflow
- ethics emission: `ethics-findings.json`
- synthesizer emission: `synthesizer-emission-v1.json`
- audit markdown: `audit-{device}.md` for v2 device output; preserve legacy `audit.md` behavior where the current scripts require it
- `priority-path-stories.json` when priority path sidecar output is produced
- `lead-reflection.md`
- `visual-report.html` when a visual report is requested

Use the path and field names from `contracts/meta-schema.md`, `contracts/audit-state-machine.md`, and the relevant workflow. Do not invent alternate artifact names.

## Validation, Synthesis, and Rendering

This skill runs the **v2 JSON-emission pipeline**: specialists, ethics, and the synthesizer emit structured JSON (`cluster-{cluster}-{device}.json`, `ethics-findings.json`, `synthesizer-emission-v1.json`) and hotspots resolve by `e_index` lookup. Run these steps in order once specialist and ethics emissions exist. Commands run from the repo root; substitute `{id}`, `{cluster}`, `{device}`, and `{plugin-root}`. The exact synthesizer dispatch wiring (canonical-f_refs file plumbing, prompt placeholders) lives in the Synthesis-phase contracts (`contracts/synthesizer-subagent.md`, `contracts/priority-path-synthesis.md`); the steps below are the orchestration spine and the commands that are stable regardless of that wiring.

1. **Validate every specialist + ethics emission** (P0-08), one call per emission:
   ```powershell
   python scripts/test-specialist.py validate --emission-path docs/ecp/{id}/cluster-{cluster}-{device}.json --schema cluster-emission --baton-path docs/ecp/{id}/baton.json
   ```
   Validate the ethics emission against both batons (`--schema cluster-emission --desktop-baton-path ... --mobile-baton-path ...`). On failure, **first try autofix** (G15 P1-3) for known-safe shape traps catalogued from live runs (path-form telemetry, duplicate finding tuples, overlong `proposed_anchor.reason`, missing `proposed_anchor` on absent findings):
   ```powershell
   python scripts/test-specialist.py autofix --emission-path docs/ecp/{id}/cluster-{cluster}-{device}.json --in-place
   ```
   Re-run `validate` against the autofixed emission. If validation now passes, proceed (the `--in-place` repairs were semantically conservative and the repairs log is at `<emission>.repairs.json`). If validation still fails, pass `--write-retry-prompt <path>` and re-dispatch the specialist; never hand-edit an emission beyond what autofix repaired.

2. **Build the canonical f_refs manifest** (after all specialists + ethics validate):
   ```powershell
   python scripts/lead_prep.py build-canonical-frefs --engagement docs/ecp/{id}
   ```
   Writes `canonical-f-refs.json` (`{valid_refs, by_canonical_ref}` — the shape steps 4-5 consume) plus `canonical-f-refs-manifest.json` + `.md` (tooling + the markdown the synthesizer prompt inlines). All three are serialized from one `report/v2_loader.build_canonical_view` call, so they are exactly the renderer's allowlist and cannot drift. These are the canonical f_refs the synthesizer must cite.

3. **Trim each device baton to referenced elements** before synthesizer dispatch (mandatory — prevents 1M-context overflow). Use `scripts/assembly/synth_input.trim_baton_file`, which writes a trimmed baton plus a `baton-{device}-trimmed-summary.json` sidecar. The synthesizer prompt points at the trimmed batons.

4. **Prepare and dispatch the synthesizer** (Task subagent) per `contracts/synthesizer-subagent.md`, feeding it the cluster emissions, ethics findings, the trimmed batons (step 3), and the canonical f_refs (step 2):
   ```powershell
   python scripts/test-specialist.py prepare-synthesizer --engagement-id {id} --cluster-emission docs/ecp/{id}/cluster-{cluster}-{device}.json --ethics-findings-path docs/ecp/{id}/ethics-findings.json --desktop-baton-path <trimmed-desktop-baton> --mobile-baton-path <trimmed-mobile-baton> --canonical-f-refs-path docs/ecp/{id}/canonical-f-refs.json --out docs/ecp/{id}/.prompts/synthesizer.txt
   ```
   (`--cluster-emission` is repeated once per emission.) The synthesizer emits `synthesizer-emission-v1.json` plus `audit-desktop.md` / `audit-mobile.md`.

5. **Validate the synthesizer emission** (Phase F.4) against the canonical f_refs allowlist:
   ```powershell
   python scripts/test-specialist.py validate --emission-path docs/ecp/{id}/synthesizer-emission-v1.json --schema synthesizer-emission --finalized-findings docs/ecp/{id}/canonical-f-refs.json
   ```

6. **Run the cross-device drift gate** (Phase F.3):
   ```powershell
   python scripts/test-specialist.py drift-check --desktop-md docs/ecp/{id}/audit-desktop.md --mobile-md docs/ecp/{id}/audit-mobile.md --synthesizer-emission docs/ecp/{id}/synthesizer-emission-v1.json
   ```

7. **Run substantive canaries** with `scripts.assembly.canary_checks.run_all_canaries` as documented in `contracts/trace-assertion-canary.md`; append summaries to `audit-trace.log` and record anomalies in `lead-reflection.md`.

8. **Render the visual report** (v2 is auto-detected from `synthesizer-emission-v1.json`; `--v2` forces it), one call per device:
   ```powershell
   python scripts/generate-report.py --v2 --engagement docs/ecp/{id} --device {device} --plugin-root {plugin-root} --audit audit-{device}.md
   ```

**Legacy v1 tools — do NOT run on a v2 engagement.** `scripts/validate-cluster-files.py`, `scripts/assemble-audit.py`, and `scripts/prep_synth_input.py` parse v1 `cluster-{cluster}-{device}.md` markdown. On a v2 JSON engagement they find zero findings or raise `FileNotFoundError`; they exist only for replaying archived v1 markdown engagements. The v1 `audit.md` template lives in `contracts/audit-assembly.md`.

**Recovery.** If acquisition fails after the required dispatch and correction attempt, use the manual acquisition fallback from `workflows/acquire.md` and log the degraded path. If cluster specialists fail, write an honest SKIP marker; do not replace specialist work with lead-authored findings.

## Checkpoints

Use checkpoint wording and options from the loaded workflow:

- Audit checkpoint: summary, key highlights, progress comparison when available, export options.

`--auto` runs straight through to the report without pausing at the audit checkpoint.

## Exit Criteria

An audit phase can move forward only when:

- acquisition artifacts for requested devices have been verified;
- selected cluster emissions exist or skipped clusters are explicitly recorded;
- ethics has run or has a logged partial status after allowed retry;
- synthesis has produced expected v2 outputs or has a logged failure path;
- pre-assembly validation and assembly have run;
- structural assertions have passed;
- substantive canary results and lead reflection are written.

The audit is complete when findings, the Priority Path, any requested exports (audit markdown + visual report), `meta.json`, `audit-trace.log`, and `lead-reflection.md` all reflect the final state.

The generated report always ships as a **DRAFT** (`meta.json` `report_state: "draft"`, per `contracts/meta-schema.md` / product.md §6). Never write `report_state: "client-verified"` from the audit flow — and never under `--auto`. Client-ready promotion is the operator's manual verification pass (re-check the live site, follow every legal/ethics citation link, finalize hotspot placement), run separately via `generate-report.py --engagement <dir> --mark-client-verified`.

The `lead-reflection.md` narrative ALSO ships as a **DRAFT** (`meta.json` `reflection_state: "draft"`, per `contracts/meta-schema.md` / G23, 2026-05-28). After the canaries pass and the reflection narrative has been written/refreshed against the actually-completed on-disk state, the lead invokes `generate-report.py --engagement <dir> --mark-reflection-complete` to attest that the narrative matches the pipeline's actual end-state. This is the explicit verb the G23 state machine gates on; **never write `reflection_state: "complete"` directly or under `--auto`.** Premature reflection writes (e.g. an agent acting on a stale-partial pipeline view) leave the state at `draft`, so the operator knows at a glance whether the narrative is finalized.
