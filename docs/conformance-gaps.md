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

### G1 · P2 · Findings missing the `at e{baton_index}` anchor format
- **Spec:** every finding element-anchored; the renderer derives refs from anchors.
- **Now:** live run soft-canary `element_index_match_rate = 0.68` (<0.80). ~15
  markdown ELEMENT lines describe the element without the `at eN` suffix; hotspots
  still resolved structurally, but the format drifts.
- **Fix:** reinforce `contracts/synthesizer-v2.md` to always render `at e{baton_index}`
  for present-element findings. Raise the canary threshold once clean.

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

### G6 · P2 · Oversized exact-element hotspots not auto-down-ranked
- **Spec:** §4.2 precision-first.
- **Now:** soft canaries `giant_exact_rectangles` (desktop 4/28, mobile 2/14) and
  `proxy_overload` (50% / 74%) flag low-precision markers but still render them.
- **Fix:** auto-down-rank exact-element markers whose baton rect exceeds a size
  threshold (e.g., >85%w/70%h) to a proxy/section anchor.

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

### G15 · P1/P2 · Emission-bounce friction, ethics jurisdiction, screenshot note
- **P1-3 (bounce rate, 5/13 retries):** anchor-candidate registry friction
  (specialist cites a real `eN` not in the candidate registry); the
  `proposed_anchor.reason` ≤200-char cap isn't surfaced inline in
  `contracts/specialist-prompt-v2.md`; ethics-emission shape traps (path-form
  telemetry, missing `proposed_anchor` on absent findings). Tighten prompts / add
  a small ethics-emission autofix.
- **P1-4 (ethics jurisdiction):** ethics cited GDPR for a US-targeted page; add a
  "match citation to the page's jurisdiction (US→CCPA/FTC, EU→GDPR gated on
  hreflang)" steer to `contracts/ethics-subagent-v2.md`. (Overlaps G2/G9.)
- **P2-3:** note in `workflows/acquire.md` that `--screenshot-quality` is
  session-global — set it before the first capture.

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
5. **← START HERE — G1 / G6 / G15** (hotspot precision + emission-bounce +
   ethics-jurisdiction tuning) — reduce manual editing and retries per audit.
6. **G2** (citation/legal re-audit) — elevate any legal-claim fix to P1.
7. ~~**G5** (editor UX)~~ — ✓ DONE (`0194e90`); taken out of order (Dan's call). The
   manual-placement queue now drains as you place.
8. **G3 / G9 / G10** — low-priority hardening + cosmetics.
