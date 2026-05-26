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

### G4 · P1 · Hotspot fallback auto-places a banner instead of leaving blank
- **Spec:** §4.2 — auto-place only at ~99.9% confidence; **below threshold leave it
  blank** for manual placement; never auto-place a guess; a wrong/low-confidence
  placement is worse than a blank.
- **Now:** `scripts/report/v2_markers.py` runs a placement ladder ending in
  **"banner (last resort) — render at a top-of-page banner indicator."** That is an
  auto-placed guess, not a blank. (The live run happened to place 0 banners, so it
  didn't bite — but the behavior contradicts the spec.)
- **Fix:** add a confidence gate — below threshold, emit the finding with **no
  hotspot**, queued into the editor's manual-placement list, instead of a banner.
  This is the core §4.2 behavior and the highest-value presentation fix.

### G5 · P2 · Editor manual-placement ergonomics
- **Spec:** §4.2 — the edit tool must make creating/placing/erasing hotspots *easy*
  (manual placement is a designed step, esp. for absence findings).
- **Now:** `tools/editor/` exists and is wired, but the create-from-scratch UX was
  flagged (during the design grill) as needing to be dialed in.
- **Fix:** review `tools/editor/editor.js` for one-click create/place/erase; needs
  an operator UX pass (Dan).

### G6 · P2 · Oversized exact-element hotspots not auto-down-ranked
- **Spec:** §4.2 precision-first.
- **Now:** soft canaries `giant_exact_rectangles` (desktop 4/28, mobile 2/14) and
  `proxy_overload` (50% / 74%) flag low-precision markers but still render them.
- **Fix:** auto-down-rank exact-element markers whose baton rect exceeds a size
  threshold (e.g., >85%w/70%h) to a proxy/section anchor.

---

## §2.2 — Input scope

### G7 · P1 · Audit skill still supports File + Description modes
- **Spec:** §2.2 — **URL is the only canonical input** (screenshot-only and codebase
  are frozen).
- **Now:** `skills/audit/SKILL.md` Mode Selection lists URL / File / Description
  modes; `argument-hint` says `[url-or-file-path]`.
- **Fix:** tighten the audit skill to URL-only (remove/deprecate File + Description
  handling and the hint), **or** — if you want exported-HTML/file input — that's a
  deliberate §2.2 Spec Change Log entry first, then conform. Decision needed.

---

## §6 — Draft → client-ready verification gate

### G8 · P1 · Gate is documented but not implemented
- **Spec:** §6 — a report is DRAFT until a manual verification pass; the state is
  **tracked** (`meta.json`: `draft | client-verified`); `--auto` can never mark
  client-ready.
- **Now:** `contracts/meta-schema.md` has **no** such state; nothing tracks or
  enforces it. The gate lives only in the operator's habit.
- **Fix:** add a `report_state` (or `client_verified`) field to the meta schema;
  set it only on the manual verification pass (re-check site + citation links +
  finalize hotspots); assert `--auto` cannot set it.

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

### G11 · P1 · SKILL router documents the v1 pipeline for v2 work
- **Now:** `skills/audit/SKILL.md` "Validation And Recovery" tells the lead to run
  `validate-cluster-files.py` + `assemble-audit.py` — both v1 markdown-path tools.
  On a v2 (JSON-emission) engagement they no-op or crash (`prep_synth_input.py`
  raises `FileNotFoundError` expecting `.md`). The real v2 path
  (`test-specialist.py validate` → `lead_prep build-canonical-frefs` →
  `synth_input.trim_baton_file` → synthesizer → `generate-report.py --v2`) isn't
  documented; the lead discovered it by reading code.
- **Fix:** add a v2-pipeline subsection (or `workflows/assemble-v2.md`) with the
  real commands/order; mark the v1 tools v1-only with pointers.

### G12 · P1 · Claude acquirer (`workflows/acquire.md`) has no base64 eval guard
- **Now:** the earlier Windows eval fix (base64 + `_unwrap_eval`) was applied to
  `scripts/cursor_bootstrap_url.py` — the **Cursor/standalone** path. The Claude
  `/ecp:audit` acquirer follows `workflows/acquire.md`, which runs `agent-browser
  eval` **directly via Bash** (no base64). It worked in the live run only because
  the Bash tool uses the *bash* shim (no PowerShell `\"` mangling) — dodged by
  environment luck, not design.
- **Fix:** steer `workflows/acquire.md` to use `agent-browser eval -b <base64>`
  (or `--stdin`) for any non-trivial JS, mirroring `_eval_args` in
  `cursor_bootstrap_url.py`. Bundle with G11.

### G13 · P1 · Non-ASCII in canary summaries crashes the Windows console
- **Now:** `scripts/assembly/canary_checks.py` has ~30 non-ASCII chars (`→` etc.);
  printing on a cp1252 Windows console raises `UnicodeEncodeError`. Operator is on
  Windows. (Confirmed via grep.)
- **Fix:** ASCII (`->`) in summary strings, or `sys.stdout.reconfigure(encoding=
  "utf-8")` at CLI entrypoints. Sweep `print()` strings repo-wide for non-ASCII.

### G14 · P1 · Acquirer emits negative rect coords; schema rejects them
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

## Suggested order

1. **G11 + G12** (v2-pipeline doc + acquirer base64 guard) — bundle; prevents the
   next lead from rediscovering the v2 path and hardens the acquirer.
2. **G13 + G14** (Windows unicode crash + negative-coord clamp) — cheap, and both
   bit the live run on a Windows operator.
3. **G4** (hotspot blank-below-confidence) and **G8** (client-ready gate) — the two
   P1 *behavioral* gaps that back §4.2 and §6 trust invariants.
4. **G7** (URL-only) — decide conform vs. spec-change, then act.
5. **G1 / G6 / G15** (hotspot precision + emission-bounce + ethics-jurisdiction
   tuning) — reduce manual editing and retries per audit.
6. **G2** (citation/legal re-audit) — elevate any legal-claim fix to P1.
7. **G5** (editor UX) — needs an operator pass.
8. **G3 / G9 / G10** — low-priority hardening + cosmetics.
