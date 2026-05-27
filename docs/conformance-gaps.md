# Conformance gaps — code/docs vs `product.md`

**Generated:** 2026-05-26 · **Spec baseline:** `product.md` v1.0

This is the **tuning roadmap**: where the current code/docs diverge from what
`product.md` already declares. Every item here is **conformance** work (the spec
is the target; the code is the gap) — *not* a spec change. Closing these does not
require a Spec Change Log entry. Re-adding frozen modes or new capability would —
that's explicitly out of scope here.

Severity: **P1** = spec'd invariant unimplemented or a notable divergence ·
**P2** = quality tuning toward a declared bar · **P3** = cosmetic.

---

## Already conformant (no action)

- §1 identity (Claude-only runtime), §2.4 audit stops at report, §2.3 all 10
  cluster specialists present, §5 frozen scope (zero dangling sibling-skill refs
  repo-wide), §8 runtime (Codex/Cursor archived). Validated by the 2026-05-26
  live audit + 403-test suite.

---

## §4.1 — Content trust (is the *finding* valid?)

### G1 · P2 · ◐ PROMPT STEER LANDED (`cec2794`), validate on live run · Findings missing the `at e{baton_index}` anchor format
- **Spec:** every finding element-anchored; the renderer derives refs from anchors.
- **Was:** live run soft-canary `element_index_match_rate = 0.68` (<0.80). ~15
  markdown ELEMENT lines described the element without the `at eN` suffix; hotspots
  still resolved structurally, but the format drifted.
- **Done (steer):** `contracts/synthesizer-v2.md` ELEMENT guidance now makes the
  `at e{baton_index}` suffix **mandatory** for present-element findings and names the
  `element_index_match_rate` canary that fails on drift.
- **Remaining (needs live run):** confirm the next run's `element_index_match_rate`
  ≥ 0.80, then raise the canary threshold once clean.

### G2 · P2 (P1 for any legal claim) · Citation/tier integrity re-audit
- **Spec:** §4.1 — misquoted/over-applied law is the *highest-bar* violation;
  citations must support the exact claim.
- **Now:** the reference library carried over unchanged; the April full-scope
  review flagged specific issues (a Baymard form-field number not matching source,
  legal/lawsuit data tiered `Gold`, "28 regulations" vs 21 primary rows, CPPA/EU-AI-Act
  date drift). Not yet re-verified in the clean repo.
- **Fix:** targeted re-audit of quantitative + legal citations in `references/`
  and `citations/sources.md`; downgrade over-tiered legal claims; correct numbers
  to source. Treat legal-claim accuracy as P1.

### G3 · P3 · "DOM-present-but-not-displayed" not formally gated
- **Spec:** §4.1 — a visibility claim must reflect the *rendered* page, not raw markup.
- **Now:** mitigated (acquirer captures rendered state + screenshots; specialist
  evidence-anchor gate requires a page anchor) but there's no explicit check that a
  visibility claim matches rendered state.
- **Fix:** optional — add a canary that flags findings asserting absence/visibility
  without a screenshot-region or rendered-style anchor.

---

## §4.2 — Presentation trust (does the *report* point at the right thing?)

### G4 · P1 · ✓ DONE (`7a11876`) · Hotspot fallback auto-places a banner instead of leaving blank
- **Spec:** §4.2 — auto-place only at ~99.9% confidence; **below threshold leave it
  blank** for manual placement; never auto-place a guess; a wrong/low-confidence
  placement is worse than a blank.
- **Was:** `scripts/report/v2_markers.py` ran a placement ladder ending in
  **"banner (last resort) — render at a top-of-page banner indicator."** That was an
  auto-placed guess, not a blank. (The live run happened to place 0 banners, so it
  didn't bite — but the behavior contradicted the spec.)
- **Done:** Strategy 4 renamed `banner` → `unplaced`; emits **no position**
  (`fallback_position=None`). `compute_marker_positions_v2` renders nothing, and
  `review_state` builds a hidden, coord-less marker (mirroring the editor's own
  `clearActiveMarkerPlacement`) with `hotspot_confidence="needs-manual-marker"` so
  the finding lands in the editor's "Place manually" queue. Visual-evidence kept at
  `page_level/low` (the prior banner footprint) so the Phase-3 priority-path gate is
  unchanged — scoped to the §4.2 blank-vs-guess fix. `banner` mappings retained for
  back-compat. Browser-free regression: `tests/test_g4_blank_below_confidence.py`.

### G5 · P2 · ✓ DONE (`0194e90`) · Editor manual-placement ergonomics
- **Spec:** §4.2 — the edit tool must make creating/placing/erasing hotspots *easy*
  (manual placement is a designed step, esp. for absence findings).
- **Was:** `tools/editor/` was wired, but hand-drawing a hotspot never cleared a
  finding's `needs-manual-marker` state — the "Place manually" queue never drained, so
  the operator couldn't tell what was left to place (esp. the G4 absence findings now
  routed there).
- **Done:** `setMarker` promotes a hand-placed finding off `needs-manual-marker` →
  `exact-selector` (mirrors snap, which already did this); added a one-click **Place**
  queue listing everything awaiting a hotspot; added a stage hint when the active
  finding is unplaced. Playwright smoke (`tests/editor-smoke.mjs`) covers the
  clear→place round-trip; both smokes green. (`tools/editor/CHANGELOG.md` v1.0.3.)

### G6 · P2 · ✓ DONE (`cf1b699`) · Oversized exact-element hotspots not auto-down-ranked
- **Spec:** §4.2 precision-first.
- **Was:** soft canaries `giant_exact_rectangles` (desktop 4/28, mobile 2/14) and
  `proxy_overload` (50% / 74%) flagged low-precision markers but still rendered them
  as solid "exact" rects.
- **Done:** `auto_map_markers_v2` down-ranks an `exact_element` mapping to
  `proxy_element` (low confidence, renders dashed) when the baton rect exceeds
  `GIANT_EXACT_WIDTH_PCT`/`HEIGHT_PCT` (85%w/70%h) of the viewport. The threshold
  equals the `giant_exact_rectangles` gate threshold (a test asserts they stay in
  sync), so that gate now reports zero violations. Note: this intentionally nudges
  `proxy_overload` up — those markers *are* approximate; suppressing it would game
  the metric. Regression: `tests/test_g6_oversized_downrank.py`.

---

## §2.2 — Input scope

### G7 · P1 · ✓ DONE (`5d569a6`) · Audit skill still supports File + Description modes
- **Spec:** §2.2 — **URL is the only canonical input** (screenshot-only and codebase
  are frozen).
- **Was:** `skills/audit/SKILL.md` Mode Selection listed URL / File / Description
  modes; `argument-hint` said `[url-or-file-path]`.
- **Done (decision: conform to URL-only):** Mode Selection is URL-only; `argument-hint`
  is `[url]`; the `contracts/lead-discipline.md` mode-detection prompt asks for a URL.
  File + Description modes removed from the audit path (Description was build/from-
  scratch residue regardless). Frozen inputs stay frozen (§5); the `meta.json`
  `source_mode` enum is left intact (shared contract still serving the frozen modes) —
  conformance, not a spec change.

---

## §6 — Draft → client-ready verification gate

### G8 · P1 · ✓ DONE (`5f34833`) · Gate is documented but not implemented
- **Spec:** §6 — a report is DRAFT until a manual verification pass; the state is
  **tracked** (`meta.json`: `draft | client-verified`); `--auto` can never mark
  client-ready.
- **Was:** `contracts/meta-schema.md` had **no** such state; nothing tracked or
  enforced it. The gate lived only in the operator's habit.
- **Done:** `report_state` (`draft | client-verified`, default `draft`, missing reads
  as `draft`) added to `contracts/meta-schema.md` + `templates/meta.json.template`.
  New `scripts/assembly/report_state.py`: `read_report_state()` (defaults draft) and
  `set_client_verified(meta_path, *, auto)` which raises `AutoPromotionError` when
  `auto=True` — the §6 invariant enforced in code. `meta_validator` warns on a bad
  enum. `generate-report.py --mark-client-verified` is the operator's manual-pass
  verb (+ an `--auto` flag the guard refuses). `skills/audit/SKILL.md` steers the
  report to ship as `draft`, never promoted from the audit flow / under `--auto`.
  Browser-free regression: `tests/test_g8_client_verified_gate.py`.

---

## §3 — ISN'T boundaries (framing spot-check)

### G9 · P3 · Verify output copy honors the ISN'T list
- **Spec:** §3 — not a measurement/testing tool; not an exhaustive technical auditor;
  not legal/compliance advice; not a crawler/auto-fixer.
- **Now:** mostly holds (single URL; ethics caught a GDPR→CCPA overreach at runtime).
- **Fix:** spot-check report templates + `references/ethics-gate.md` copy for any
  "we measure conversion / guarantee lift / certify compliance" phrasing; add the
  "informational, not legal advice" disclaimer to legal/ethics findings if absent.

---

## Cosmetic

### G10 · P3 · Inert `# docs/plans/…` provenance comments
- ~23 files in `scripts/`, `tests/`, `schema/` carry comments pointing at archived
  plan docs. Never loaded into agent context; harmless. Scrub opportunistically.

---

## Run-observed robustness (from the 2026-05-26 live-audit handoff)

Source: `docs/2026-05-26-ecp-v2-run-observations-handoff.md` — observed during the
live run, not from spec/code reading. That handoff's **P0-1 (canonical-fref drift)
is already FIXED** (commit `caea832` + `tests/test_canonical_frefs_parity.py`). The
rest, verified against current `HEAD`:

> **Status (2026-05-26 session 2): G11, G12, G13, G14 are ✓ DONE** — commits
> `763065b` (G11+G12) and `65c1c93` (G13+G14), each with a browser-free regression
> test. **G15 remains.** See "Post-migration completeness" below for additional
> drops resolved this session.

### G11 · P1 · ✓ DONE (`763065b`) · SKILL router documents the v1 pipeline for v2 work
- **Now:** `skills/audit/SKILL.md` "Validation And Recovery" tells the lead to run
  `validate-cluster-files.py` + `assemble-audit.py` — both v1 markdown-path tools.
  On a v2 (JSON-emission) engagement they no-op or crash (`prep_synth_input.py`
  raises `FileNotFoundError` expecting `.md`). The real v2 path
  (`test-specialist.py validate` → `lead_prep build-canonical-frefs` →
  `synth_input.trim_baton_file` → synthesizer → `generate-report.py --v2`) isn't
  documented; the lead discovered it by reading code.
- **Fix:** add a v2-pipeline subsection (or `workflows/assemble-v2.md`) with the
  real commands/order; mark the v1 tools v1-only with pointers.

### G12 · P1 · ✓ DONE (`763065b`) · Claude acquirer (`workflows/acquire.md`) has no base64 eval guard
- **Now:** the earlier Windows eval fix (base64 + `_unwrap_eval`) was applied to
  `scripts/cursor_bootstrap_url.py` — the **Cursor/standalone** path. The Claude
  `/ecp:audit` acquirer follows `workflows/acquire.md`, which runs `agent-browser
  eval` **directly via Bash** (no base64). It worked in the live run only because
  the Bash tool uses the *bash* shim (no PowerShell `\"` mangling) — dodged by
  environment luck, not design.
- **Fix:** steer `workflows/acquire.md` to use `agent-browser eval -b <base64>`
  (or `--stdin`) for any non-trivial JS, mirroring `_eval_args` in
  `cursor_bootstrap_url.py`. Bundle with G11.

### G13 · P1 · ✓ DONE (`65c1c93`) · Non-ASCII in `print()` literals crashes the Windows console
- **Now:** `scripts/assembly/canary_checks.py` has ~30 non-ASCII chars (`→` etc.);
  printing on a cp1252 Windows console raises `UnicodeEncodeError`. Operator is on
  Windows. (Confirmed via grep.)
- **Fix:** ASCII (`->`) in summary strings, or `sys.stdout.reconfigure(encoding=
  "utf-8")` at CLI entrypoints. Sweep `print()` strings repo-wide for non-ASCII.
- **Done note:** `canary_checks.py` was actually safe (`json.dumps` escapes
  non-ASCII); the real offenders were 23 `print()` em-dash literals across 7 scripts.
  ASCII-swept + repo-wide lint `tests/test_no_nonascii_in_script_prints.py`.

### G14 · P1 · ✓ DONE (`65c1c93`) · Acquirer emits negative rect coords; schema rejects them
- **Now:** off-canvas elements yield `getBoundingClientRect` negatives (e.g.
  `rect.x = -13`); `schema/baton-v1.json` sets `rect.x/y minimum: 0`, so the baton
  fails validation and the lead clamped by hand. (Confirmed.)
- **Fix:** clamp negative `x/y` to 0 at the source (acquirer extraction step) —
  cleaner than relaxing the schema.

### G15 · P1/P2 · ◐ PARTIAL (`cec2794`) · Emission-bounce friction, ethics jurisdiction, screenshot note
- **P1-4 (ethics jurisdiction) — ✓ DONE (`cec2794`):** added a "Jurisdiction matching"
  rule to `contracts/ethics-subagent-v2.md` (US→FTC/CCPA, EU→GDPR/ePrivacy/DSA gated
  on hreflang/footer; prefer CLEAR/ADJACENT when targeting is ambiguous; GDPR-on-US
  page = misapplied-law §4.1 error). Fixes the observed GDPR-on-US-page drift.
- **P2-3 — ✓ DONE (`cec2794`):** `workflows/acquire.md` now notes `--screenshot-quality`
  /`set screenshot-quality` is session-global — set before the first capture.
- **P1-3 (bounce rate, 5/13 retries) — REMAINING, needs live run:** the
  `proposed_anchor.reason` ≤200-char cap is already surfaced at
  `specialist-prompt-v2.md` field rules (line ~359). Still open: anchor-candidate
  registry friction (specialist cites a real `eN` not in the candidate registry) and
  ethics-emission shape traps (path-form telemetry, missing `proposed_anchor` on
  absent findings) → add a small ethics-emission autofix and re-measure bounce rate
  against a live run.

---

## Trust integrity (2026-05-27 session 4)

### G18 · P2 · ✓ DONE (this branch) · Drift-gate why-slice absorbs trailing per-device sections
- **Spec:** §4.1 — synthesis drift is a real signal; false-positive drift is a trust cost
  on the operator (cried wolf) and an audit-blocker if it phase-fails when nothing is
  actually wrong.
- **Was:** [scripts/assembly/synth_input.py](scripts/assembly/synth_input.py)
  `extract_finding_prose` sliced from the finding heading to the next *finding* heading
  (3-4 hashes named `cluster F-NN`), so the LAST finding's body slice ran to EOF. The
  `_slice_section` within-body terminator only stopped at the next `\n\n**[A-Z]` bold
  header. If the synthesizer wrote `## Methodology Notes` (or any per-device appendix)
  *after* the last finding and the methodology differed per device — which it usually
  does — the last finding's why-slice absorbed both methodology bodies and the drift
  gate false-fired even when the finding prose was byte-identical.
- **Evidence:** Both Run `docs/ecp/2026-05-27-af72a2ae` and Run
  `docs/ecp/2026-05-27-52f53a53` lead-reflections flagged this *independently* in the
  same session and proposed the same fix. Run B reported `ratio=0.2996 on the last
  finding`; Run C reported `0.198 on ethics F-59`. Both confirmed manually that the
  finding prose was byte-identical and the divergence was entirely in the trailing
  methodology section.
- **Done:** `extract_finding_prose`'s slice terminator now matches `^#{2,4}\s+\S+` —
  catches both finding headings and non-finding section headings (`## Methodology Notes`,
  `### Appendix`, etc.). `_slice_section` adds `\n##/\n###/\n####` as a defensive
  belt-and-suspenders terminator inside the body. Regression: 3 new tests in
  `tests/test_v2_synth_input.py::TestG18WhySliceTerminatorHardening` cover the last-
  finding-trailing-methodology case (the actual run shape), the obs/rec/why isolation
  invariant, and an intermediate-`##`-between-findings case.

### G16 · P1 · ✓ DONE (`00b1e23`) · `build_canonical_view` silently swallows schema-validation drops
- **Spec:** §0 ("never untraceable, never silently misleading") · §4.1 (every finding cited
  and anchored — but only if it's *in* the canonical view at all).
- **Was:** [scripts/report/v2_loader.py](scripts/report/v2_loader.py) `build_canonical_view`
  wrapped every `parse_emission_file` call in a bare `except Exception: continue`. Any
  cluster emission that failed the canonical-view validator was dropped from the canonical
  set with **zero observability** — no log, no canary, no trace counter. The specialist
  validator (`test-specialist.py validate --schema cluster-emission`) and the canonical-view
  validator (`assembly.json_parser.validate_emission_payload`) had drifted apart: specialists
  pass the first, fail the second, and the lead's "all 12 emissions VALID" claim was true
  for one validator while the downstream pipeline silently dropped 6 of those 12 files.
- **Evidence:** Run `docs/ecp/2026-05-27-52f53a53` (same URL as Runs A/B for n=3):
  31 raw FAIL findings emitted desktop → only 8 rendered. Two entire clusters
  (`trust-credibility`, `content-seo`) plus the desktop halves of `performance-ux` and
  `product-media` vanished. The operator received an audit billed as "comprehensive (6
  clusters)" that actually rendered findings from only 2 CRO clusters on desktop. **All
  structural assertions PASS; all substantive canaries PASS.** Exact §0 untraceable-misleading
  failure mode.
- **Done (Layer 1 — surface the drops):** `build_canonical_view` now returns a 3-tuple
  `(by_canonical_ref, merge_aliases, dropped_emissions)`. Each dropped emission carries
  `{path, error_type, error_message}`. `lead_prep.py build-canonical-frefs` always writes
  `canonical-frefs-dropped.json` (empty list on a clean run so downstream tooling has a
  stable file) and exits code **4** when drops occurred — phase-blocks the audit. All four
  production callers + four test callers updated to the new return shape.
- **Done (Layer 2 — clusters_represented canary):** New
  `assembly.canary_checks.check_clusters_represented` reads `meta.json["clusters_used"]`
  and `canonical-f-refs.json["valid_refs"]`; hard-fails if any requested CRO cluster has
  zero canonical refs OR if `canonical-frefs-dropped.json["dropped_count"] > 0`. Wired into
  `run_all_canaries` as canary #5. Catches both the strong signal (cluster missing) and
  the weaker-but-real signal (drop file non-empty even when surviving emissions cover all
  clusters).
- **Regression:** `tests/test_g19_canonical_view_surfaces_drops.py` (5 tests: 3-tuple
  contract, clean-run-empty-drops, invalid-cluster-recorded, CLI clean exit, CLI dropped
  exit-4). `tests/test_g19_clusters_represented_canary.py` (8 tests: pass + fail + skip
  cases including the headline Run C shape). Both unittest-style for `unittest discover`
  runner.
- **Layer 3 (deferred):** schema reconciliation — make the specialist validator and the
  canonical-view validator share a single source of truth so this drift can't recur. Tracked
  separately; Layers 1+2 make Layer 3 non-urgent because the failure is no longer silent.

---

## Post-migration completeness (2026-05-26 session 2) · ✓ DONE

Migrating from the larger plugin dropped several referenced scripts/fixtures that
the canonical `unittest discover` runner didn't catch (it silently skips
pytest-style tests). Swept systematically + cross-checked vs the archive; all resolved:

- **`build_canonical_f_refs.py`** (dropped) → consolidated into `lead_prep
  build-canonical-frefs`, which now writes both `canonical-f-refs.json` (consumer
  shape) and the manifest from one `build_canonical_view` call (`fc96777`).
- **`build_synthesizer_emission_fallback.py`** (dropped) → restored from archive (`3431c61`).
- **3 dev-engagement fixtures:** 2 editor-smoke fixtures restored to `tests/fixtures/`;
  the 50 MB review-state engagement skip-guarded (`05c9883`).
- **Stale `build_canonical_f_refs.py` references** scrubbed; Cursor `next_steps` stale
  guidance removed (`831b66e`).
- The 2 `.cursor-plugin/` scripts (`validate_meta.py`, `ecp_run_visual_reports.py`) are
  deliberate non-canonical drops (§8) — NOT restored.

**Verify BOTH runners:** `unittest discover` → 422 pass / 1 skip; `pytest tests/` →
692 pass / 12 skip / 0 fail. (unittest alone hides pytest-style breakage.)

---

## Suggested order

1. ~~**G11 + G12** (v2-pipeline doc + acquirer base64 guard)~~ — ✓ DONE (`763065b`).
2. ~~**G13 + G14** (Windows unicode crash + negative-coord clamp)~~ — ✓ DONE (`65c1c93`);
   plus post-migration completeness (above) — ✓ DONE.
3. ~~**G4** (hotspot blank-below-confidence) and **G8** (client-ready gate)~~ —
   ✓ DONE (`7a11876`, `5f34833`); the two P1 *behavioral* gaps backing §4.2 and §6.
4. ~~**G7** (URL-only)~~ — ✓ DONE (`5d569a6`); decision was conform-to-URL-only (no
   spec change). All P1 gaps are now closed.
5. **← START HERE (needs a live audit run) — validate G1 + finish G15 P1-3.** The safe
   prompt steers are in (`cec2794`): G1 `at eN` reinforcement, G15 P1-4 ethics
   jurisdiction, G15 P2-3 screenshot note. A live `/ecp:audit <url>` run is now required
   to (a) confirm `element_index_match_rate` ≥ 0.80 and raise the canary threshold [G1],
   and (b) re-measure the emission bounce rate and add the ethics-emission autofix
   [G15 P1-3]. ~~G6~~ ✓ DONE (`cf1b699`).
6. **G2** (citation/legal re-audit) — needs source-checking (web). Elevate any
   legal-claim fix to P1. Overlaps the G15 P1-4 jurisdiction work already landed.
7. ~~**G5** (editor UX)~~ — ✓ DONE (`0194e90`); taken out of order (Dan's call). The
   manual-placement queue now drains as you place.
8. **G3 / G9 / G10** — low-priority hardening + cosmetics.
9. ~~**G16** (canonical-view silent drops + clusters_represented canary)~~ — ✓ DONE
   (`00b1e23`); a P1 trust-integrity fix surfaced by Run `2026-05-27-52f53a53`. Layer 3
   (schema reconciliation between specialist + canonical-view validators) remains, but is
   non-urgent now that the failure is loud.
10. ~~**G18** (drift-gate why-slice terminator harden)~~ — ✓ DONE (this branch); both
    Run B + Run C lead-reflections flagged it independently with the same root cause and
    same fix. P2 mechanical, browser-free testable. Eliminates the false-positive
    drift class where a per-device methodology section bled into the last finding's
    why-slice.
