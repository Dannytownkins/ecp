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

## Suggested order

1. **G4** (hotspot blank-below-confidence) and **G8** (client-ready gate) — the two
   P1 *behavioral* gaps that directly back §4.2 and §6 trust invariants.
2. **G7** (URL-only) — decide conform vs. spec-change, then act.
3. **G1 / G6** (hotspot precision tuning) — reduce manual editing per audit.
4. **G2** (citation/legal re-audit) — elevate any legal-claim fix to P1.
5. **G5** (editor UX) — needs an operator pass.
6. **G3 / G9 / G10** — low-priority hardening + cosmetics.
