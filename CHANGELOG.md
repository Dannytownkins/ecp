# Changelog

This repo begins at **1.0.0** as a clean prune-and-re-root. Governance and scope are
defined by `product.md`; spec-level changes are logged in its §10 Spec Change Log.
The full pre-1.0 history lives in the archived `ecommerce-conversion-psychology` repo.

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
- **Test runners:** `pytest tests/` 703 pass / 13 skip / 0 fail; `unittest discover`
  438 run / OK. G4 + G8 each ship a browser-free regression test
  (`tests/test_g4_blank_below_confidence.py`, `tests/test_g8_client_verified_gate.py`);
  G5 is covered by the Playwright editor smokes (`tests/editor-smoke.mjs` +
  `editor-server-render-smoke.mjs`, both green); G7 is doc/contract-only.

All P1 conformance gaps are closed, plus P2 G5. Remaining (per
`docs/conformance-gaps.md`) is P2/P3 tuning: **G1 / G6 / G15** (hotspot precision +
emission-bounce + ethics-jurisdiction), **G2** (citation/legal re-audit), and the P3
hardening/cosmetics (**G3 / G9 / G10**).

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
