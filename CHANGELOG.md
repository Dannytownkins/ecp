# Changelog

This repo begins at **1.0.0** as a clean prune-and-re-root. Governance and scope are
defined by `product.md`; spec-level changes are logged in its §10 Spec Change Log.
The full pre-1.0 history lives in the archived `ecommerce-conversion-psychology` repo.

## Post-1.0.0 conformance — 2026-05-27 (session 5)

Four concurrent live audits revealed (a) a real cross-engagement session-isolation
bug at the `agent-browser` layer (the headless browser session leaks across
concurrent acquirers, so one engagement's `goto` can drift another engagement's
in-flight element extraction to a different URL) and (b) a reproducible
thundering-herd rate-limit at 8+ concurrent specialist spawns. G17 closes both.

- **G17 Layer A — contamination guard** (this commit): `scripts/cursor_bootstrap_url.py`
  replaces the module-level `_ELEMENTS_JS` constant with a `_build_elements_js(
  expected_hostname)` function that bakes a `window.location.hostname` check into
  the per-section extraction JS. On mismatch, the eval returns a structured
  contamination sentinel instead of element rows; `_check_for_contamination`
  detects it and `_run_one_device` aborts with a loud STATUS line. Expected hostname
  derives from the actual landed URL (post-redirect-resolution) so www-vs-no-www
  doesn't false-trigger. `workflows/acquire.md` Step 3b documents the same guard
  pattern as MANDATORY for any acquirer (SKILL-driven or script-driven). 8 new
  unittest-style regression tests in `tests/test_acquirer_contamination_guard.py`
  including a JSON-escape-safety test against hostname-injection.
- **G17 Layer B — fan-out throttle** (this commit):
  `contracts/dispatch-contract.md` §"Why cluster specialists keep teammate
  status" point 1 rewritten to specify "waves of ≤5 concurrent spawns" with the
  empirical rationale (the 2026-05-27 batch's reproducible rate-limit at 8+
  concurrent — Amazon audit lost 7 of 8 spawns at 0 tokens; slingmods 10-cluster
  run lost its entire 20-way first wave). `skills/audit/SKILL.md` step 9 now
  references the wave cap so the audit lead waits on per-wave file-presence
  before launching the next.
- **Deferred** (out of scope here): the durable answer to the contamination
  vector is one Playwright process per engagement (no shared global state) —
  needs coordination with the upstream `agent-browser` tool, not solvable in
  this repo alone. The guard + abort is the runtime-safe stopgap.

## Post-1.0.0 conformance — 2026-05-27 (session 4)

Three live runs on the same URL (`docs/ecp/2026-05-27-b0051311`,
`2026-05-27-af72a2ae`, `2026-05-27-52f53a53`) exposed a §0 trust-integrity failure: the
canonical-view builder silently dropped schema-invalid cluster emissions, leaving Run C
with 2 of 6 CRO clusters rendered on desktop and all canaries still PASS. Closed with
G16 — see `docs/conformance-gaps.md` for the full diagnosis.

- **G16 Layer 1** (this branch): `scripts/report/v2_loader.build_canonical_view` now
  returns a 3-tuple `(by_canonical_ref, merge_aliases, dropped_emissions)`. The bare
  `except Exception: continue` that swallowed schema-validation failures pre-G16 now
  records `{path, error_type, error_message}` per drop. `scripts/lead_prep.py
  build-canonical-frefs` writes `canonical-frefs-dropped.json` on every run (empty list
  when clean so downstream canaries have a stable file) and exits code **4** when any
  emission was dropped — phase-blocks the audit. All four production callers + four
  test callers updated to the new return shape.
- **G16 Layer 2** (this branch): new `check_clusters_represented` canary in
  `scripts/assembly/canary_checks.py`. Hard-fails when any requested CRO cluster has zero
  canonical refs OR when `canonical-frefs-dropped.json` records any drops. Wired into
  `run_all_canaries` as canary #5. Would have caught Run C's coverage collapse on the
  first run instead of three runs in.
- **Regression coverage**: `tests/test_g16_canonical_view_surfaces_drops.py` +
  `tests/test_g16_clusters_represented_canary.py`. 13 unittest-style tests; both
  runners green.
- **Test runners**: `pytest tests/` and `python -m unittest discover -s tests` both
  pass green. The new G16 tests cover the 3-tuple contract, the clean-run empty-drops
  file, the dropped-run exit-4 + stderr surface, the canary's missing-cluster fail
  mode, the canary's drops-recorded fail mode, and the skip-on-pre-canonical-stage
  fixture cases.
- **G2** (this commit) — citation/legal re-audit: three of four April-flagged
  citations VERIFIED accurate via WebFetch against primary sources. (1)
  Baymard "11.3 form fields (2024 benchmark)" — confirmed at
  https://baymard.com/blog/checkout-flow-average-form-fields (Published Jun 26,
  2024). (2) EU AI Act Article 50 "effective August 2, 2026" — confirmed at
  https://artificialintelligenceact.eu/article/50/ ("Date of entry into force:
  2 August 2026" per Article 113). (3) CPPA ADMT regulations "OAL approval
  2025-09-22, effective 2026-01-01" — confirmed at
  https://cppa.ca.gov/regulations/ccpa_updates.html. (4) Open: ADA lawsuit
  count citation has a stale UsableNet URL; underlying claim not disconfirmed,
  but the source URL needs a manual update (or a Silver re-tier if UsableNet
  no longer publishes the report). The "28 regulations" item flagged by the
  April review didn't reproduce in the current repo — resolved during the
  prune-and-re-root.
- **G16 Layer 3** (this commit) — single shared validator instance: investigation
  showed the "two validators" risk was actually one validator implementation
  duplicated across `scripts/test-specialist.py` and
  `scripts/assembly/json_parser.py`. The duplicated code was byte-equivalent, but
  two copies could drift under future edits to one and not the other. New
  `assembly.json_parser.get_validator()` is the single source of truth;
  `test-specialist.py:_load_schemas()` now delegates to it. Regression test
  (`tests/test_g16_layer3_single_validator.py`) uses `assertIs` (not just
  equivalence) so any future re-introduction of a duplicate validator fails the
  gate immediately.
- **G18** (this commit): drift-gate why-slice terminator hardened. Pre-fix,
  `extract_finding_prose` in `scripts/assembly/synth_input.py` only terminated the body
  slice at the next *finding* heading; the LAST finding's slice ran to EOF and absorbed
  any trailing per-device `## Methodology Notes` section, false-firing the drift gate.
  Run B and Run C lead-reflections independently flagged this with the same fix; now
  applied. `_slice_section` also gains a defensive `\n##` terminator. 3 new regression
  tests in `tests/test_v2_synth_input.py::TestG18WhySliceTerminatorHardening` cover the
  Run-B/C reproducer, obs/rec/why isolation, and the intermediate-section case.
- **G10** (this commit): inert `docs/plans/…` provenance refs scrubbed across 17 files
  (scripts/, tests/, schema/). Bullet-list "See: - docs/plans/…" entries dropped from
  docstrings; sibling bullets pointing at live code/contracts retained. Inline
  references rewritten — e.g., `v2_loader.py` ethics-filter comment now cites
  `product.md` §4.1/§6 instead of the dead operator-mission doc; schema descriptions
  keep "Architectural fix B (2026-04-30)" labels but drop the trailing dead pointers.
- **G15 P1-3 — autofix landed** (this commit, live-run validation remaining): new
  `scripts/assembly/emission_autofix.py` applies four semantically-conservative repairs
  catalogued from the n=3 of live runs: (1) strip `references/` prefix from
  `telemetry.reference_files_read`, (2) dedup `(surface, baton_index, verdict)`
  duplicate findings (keep first), (3) cap `proposed_anchor.reason` at 200 chars
  (truncate at word boundary), (4) inject default `proposed_anchor` on absent findings
  missing one (with auto-inject marker for operator visibility). New
  `test-specialist.py autofix` CLI subcommand; `skills/audit/SKILL.md` Validation
  step 1 now runs autofix before retry-dispatch. 17 unittest-style regression tests
  (`tests/test_g15_emission_autofix.py`) covering each repair's fire + no-op cases
  plus idempotency, immutability, and combined-cases. Bounce-rate reduction will
  measure on the next live `/ecp:audit` run.

## Post-1.0.0 conformance — 2026-05-26 (session 3)

The remaining P1 gaps: the two *behavioral* gaps backing the §4.2 and §6 trust
invariants (G4, G8) plus the §2.2 input-scope gap (G7). With these, all P1
conformance gaps are closed. Roadmap and status: `docs/conformance-gaps.md`. All on
`main`.

- **G4** (`7a11876`): hotspot fallback leaves it **blank below confidence** instead of
  auto-placing a banner (`product.md` §4.2). The v2 resolver's last-resort Strategy 4
  is `unplaced` — no position; `compute_marker_positions_v2` renders nothing and
  `review_state` builds a hidden, coord-less marker tagged
  `hotspot_confidence="needs-manual-marker"`, queuing the finding in the editor's
  "Place manually" list. Visual-evidence stays `page_level/low` so the Phase-3
  priority-path gate is unchanged.
- **G8** (`5f34833`): `meta.json` now tracks `report_state` (`draft | client-verified`,
  default `draft`) per `product.md` §6. New `scripts/assembly/report_state.py`
  enforces the invariant in code — `set_client_verified(auto=True)` raises
  `AutoPromotionError`; `generate-report.py --mark-client-verified` is the operator's
  manual-pass verb and refuses under `--auto`. `meta_validator` warns on a bad enum.
- **G7** (`5d569a6`): audit input conformed to **URL-only** (`product.md` §2.2).
  Decision (Dan): conform rather than open a §2.2 Spec Change Log entry for file
  input. Mode Selection is URL-only; `argument-hint` is `[url]`; the
  `lead-discipline.md` mode-detection prompt asks for a URL. Description mode was
  build/from-scratch residue and was removed regardless. `meta.json` `source_mode`
  enum left intact (shared frozen-mode contract) — conformance, not a spec change.
- **G5** (`0194e90`, P2, taken next at Dan's call): editor manual-placement
  ergonomics — the natural completion of G4, which routes unplaced/absence findings
  into the editor with no marker. Hand-drawing a hotspot (`setMarker`) now promotes a
  finding off `needs-manual-marker` → `exact-selector` (mirrors snap), so the "Place
  manually" queue actually drains. Added a one-click **Place** queue and a stage
  placement hint. (`tools/editor/CHANGELOG.md` v1.0.3.)
- **G6** (`cf1b699`, P2): auto-down-rank oversized exact-element hotspots
  (`product.md` §4.2 precision-first). `auto_map_markers_v2` re-types an
  `exact_element` marker to `proxy_element` (dashed) when its baton rect exceeds
  85%w/70%h of the viewport — a parent-container anchor, not the subject element. The
  down-rank threshold equals the `giant_exact_rectangles` gate threshold (a test keeps
  them in sync), so that gate now passes; `proxy_overload` ticks up honestly.
- **Test runners:** `pytest tests/` 703 pass / 13 skip / 0 fail; `unittest discover`
  438 run / OK. G4 + G8 each ship a browser-free regression test
  (`tests/test_g4_blank_below_confidence.py`, `tests/test_g8_client_verified_gate.py`);
  G5 is covered by the Playwright editor smokes (`tests/editor-smoke.mjs` +
  `editor-server-render-smoke.mjs`, both green); G7 is doc/contract-only.

- **G1 + G15 prompt steers** (`cec2794`, P2): the safe pre-audit prompt/contract
  edits. G1 — `at e{baton_index}` ELEMENT suffix made mandatory in `synthesizer-v2.md`
  (names the `element_index_match_rate` canary). G15 P1-4 — Jurisdiction-matching rule
  in `ethics-subagent-v2.md` (US→FTC/CCPA, EU→GDPR; GDPR-on-US = misapplied-law). G15
  P2-3 — `acquire.md` notes `--screenshot-quality` is session-global. Effect (canary /
  bounce rates) validates on the next live run.

All P1 conformance gaps are closed, plus P2 G5 + G6 and the G1/G15 prompt steers.
Remaining (per `docs/conformance-gaps.md`) **needs a live `/ecp:audit` run**: validate
G1's `element_index_match_rate` and finish G15 P1-3 (emission-bounce autofix); **G2**
(citation/legal re-audit, needs source-checking); and P3 cosmetics (**G3 / G9 / G10** —
G10's plan-doc provenance refs are non-uniform/partly functional, explicitly harmless).

## Post-1.0.0 conformance — 2026-05-26 (session 2)

Conformance toward `product.md` + completion of the migration. Full roadmap and
status: `docs/conformance-gaps.md`. All on `main`.

- **G11 / G12** (`763065b`): the audit router now documents the real v2 pipeline
  (legacy v1 markdown tools marked v1-only); the Claude acquirer steers non-trivial
  `agent-browser eval` through base64 `-b` (mirrors `_eval_args`).
- **G13 / G14** (`65c1c93`): ASCII-swept `print()` literals + repo-wide lint
  (`tests/test_no_nonascii_in_script_prints.py`); clamp negative `rect.x/y` to 0 at
  extraction (schema keeps `minimum: 0`).
- **canonical-f-refs consolidation** (`fc96777`): `lead_prep build-canonical-frefs`
  writes both `canonical-f-refs.json` (the synthesizer-dispatch input) and the
  manifest from one `build_canonical_view` call — single source of truth.
- **Migration completeness** (`3431c61`, `05c9883`, `831b66e`): restored
  `build_synthesizer_emission_fallback.py`; restored 2 editor fixtures to
  `tests/fixtures/` + skip-guarded the 50 MB review-state engagement; scrubbed
  dangling `build_canonical_f_refs.py` references + Cursor stale `next_steps` guidance.
- **Test runners:** `unittest discover` 422/1-skip; `pytest tests/` 692/12-skip/0-fail.
  The canonical unittest runner skips pytest-style tests — run **both**.

Next conformance target (per `docs/conformance-gaps.md`): **G4** (hotspot
blank-below-confidence, §4.2) + **G8** (draft→client-ready gate, §6).

## 1.0.0 — 2026-05-26

**Clean audit-only baseline.** Pruned and re-rooted from
`ecommerce-conversion-psychology` with `product.md` as the root constitution.

- **Scope:** the canonical product is the **audit** — cited findings + Priority Path +
  annotated visual report (URL input only). The audit stops at the report.
- **Removed (archived in the old repo):** the build, compare, quick-scan, and resume
  modes; the Codex and Cursor runtimes; screenshot-only and codebase input modes;
  build-only platform guidance (`platforms/`); historical research-audit docs; stale
  scratch/worktree cruft (~660 MB).
- **Audit relay stripped** to `audit → report` per `product.md` §2.4:
  `skills/audit/SKILL.md` no longer dispatches plan/review/build; relay workflows and
  the orphaned relay contracts were deleted and runtime-loaded contracts de-referenced.
- **Install:** live development via `claude --plugin-dir <repo>` (no cache copy / sync
  step). Plugin name `ecp`, command `/ecp:audit`.

### Fixed + validated on the baseline
- **Windows acquisition** (`scripts/cursor_bootstrap_url.py`): two stacked
  `agent-browser eval` bugs — npm-shim quote/metacharacter mangling (fixed via
  base64 `eval -b`) and double-JSON-encoded results (fixed via `_unwrap_eval`).
  Regression test: `tests/test_eval_encoding.py`.
- **Stale multi-mode cross-references** scrubbed from the loaded contracts (zero
  dangling sibling-skill refs repo-wide).
- **`lead_prep build-canonical-frefs` split-brain**: now calls the renderer's
  `v2_loader.build_canonical_view` (one source of truth — ethics + dedup +
  cross-device merge). Regression test: `tests/test_canonical_frefs_parity.py`.
- **End-to-end live audit validated** on a real Shopify homepage: full relay ran
  (2 acquirers / 12 specialists / ethics / synthesizer), stopped at the report,
  **0 `(not found)` refs**, hotspots 30/30 desktop + 27/27 mobile placed.

### Known follow-ups
- Inert `# docs/plans/…` provenance comments remain in `scripts/`, `tests/`, and
  `schema/` (never loaded into agent context; cosmetic).
- Soft canaries to tighten over time: synthesizer `element_index_match_rate`
  toward 1.0; auto-down-rank oversized exact-element hotspots to proxy anchors.
