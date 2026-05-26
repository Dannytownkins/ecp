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

### Known follow-ups
- Fix the Windows acquisition bug in `scripts/cursor_bootstrap_url.py` (large-inline-JS
  `agent-browser eval` mangling) — top priority; blocks end-to-end audits on Windows.
- Clear residual provenance comments (`# docs/plans/…`) and stale sibling-skill
  cross-references left from the multi-mode era.
- Full end-to-end live-audit validation (report renders, no `(not found)` refs,
  hotspots place-or-blank) once acquisition is fixed.
