# Changelog

This repo begins at **1.0.0** as a clean prune-and-re-root. Governance and scope are
defined by `product.md`; spec-level changes are logged in its §10 Spec Change Log.
The full pre-1.0 history lives in the archived `ecommerce-conversion-psychology` repo.

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
