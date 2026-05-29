# Handoff — 2026-05-29 roadmap batch (session 8)

**Audience:** Dan (possibly on a different machine) + the next Claude. Anything not
in the committed repo is captured inline. `docs/ecp/` is gitignored.

**Previous handoff:** [docs/handoff-2026-05-28-cursor-migration-completion.md](handoff-2026-05-28-cursor-migration-completion.md).
This doc is the **delta** on top of it. Commit-by-commit detail lives in
[CHANGELOG.md](../CHANGELOG.md) "session 8" + [docs/conformance-gaps.md](conformance-gaps.md)
(G25/G26/G27/G28 + G3/G9 + Backlog #6) — **not duplicated here.**

**Session window:** 2026-05-29, one long session, machine
`C:\Users\SM - Dan\Documents\GitHub\ecp` (the "work computer" the prior §0 warned
about). This Claude window ran **no** `/ecp:audit`; Dan ran one in a *separate*
window (engagement `2026-05-29-3e7bd452`, completed) — that concurrent window is the
source of the §0 gotcha below.

---

## 0. ⚠️ READ FIRST — concurrent Claude windows share this working tree

The biggest operational hazard this session: Dan runs **two Claude windows on the
same checkout at once**. They share one working tree and `.git` index. A sibling
window ran `git switch -c fix/acquire-url-eval-comment` and committed there; that
moved `HEAD` for *this* window too, so a commit intended for `main` silently landed
on the sibling branch, and `git push origin main` reported "Everything up-to-date."

**Recovery (non-destructive):** cherry-picked the commit onto `main` via a throwaway
`git worktree add <tmp> main`, pushed, removed the worktree, then merged the sibling's
real work and deleted its branch. Nothing was lost.

**How to avoid:** run `git branch` immediately before any `git add`/`commit`/`push`;
stage **explicit file paths**, never `git add -A`. Saved as memory
`ecp-shared-checkout-branch-collision` (see `memory/MEMORY.md`).

---

## 1. Where `main` is

Tip **`853138d`**. Both runners green: `pytest tests/` → **867 passed, 12 skipped,
54 subtests**; `python -m unittest discover -s tests` → **566 ran, 1 skipped**.

## 2. What closed this session (one line each — see CHANGELOG/conformance-gaps for full detail)

- Repo hygiene (`e08ea70`): removed the misnamed `--quality` PNG; gitignored
  per-engagement baton scratch; `/--*` root guard.
- **Durable v1→v2 baton converter** `scripts/baton_v1_to_v2.py` (spec `f77cea4`;
  code `d32cec2` → `0c69dea` → `9bbe977`, **G26**) — supersedes the throwaway
  `adapt_v1_baton_to_v2.py` and the per-engagement `convert_*_batons.py` copies.
- **Lead-reflection-stale canary** `26db34c` (**G25**) + **file-ownership check**
  (`63d389a` canary + `3cc04c0` specialist-prompt prohibition, **G28**).
- **Acquire SyntaxError fix** `90030d0` (**G27**) — authored by the concurrent
  window, merged here (see §3).
- **Backlog #6** `1296f77` — `visual_quality` all-zeros investigated + regression
  guard (see §3).
- **G3/G9** `853138d` (P3) — G3 documented as covered; G9 report disclaimer added.
- Ledger commits: `1cc245f`, `e6c1f2b` (+ inline notes in the above).

## 3. Carry-across findings (NOT in the commits — and validated against gitignored data)

These were validated against `docs/ecp/2026-05-29-3e7bd452` — a **complete real v2
engagement that is gitignored and will NOT exist on another machine.** Summarized so
they survive the move:

- **Converter cluster policy:** a baton's per-section `clusters` array is **advisory**
  — `dom_preprocess._route_clusters_for()` (≈ `dom_preprocess.py:418`) re-routes
  authoritatively from section labels; the prototypes' all-6-clusters stamp was inert.
  The converter mirrors `acquire_url.py` (reuses `ecp_section_hints`), preserving v1
  clusters / enriching only when empty. Read-only validation reproduced the real v2
  baton: 0 schema errors; elements/sections/page_head/page_height matched.
- **`visual_quality` all-zeros root cause:** older v2 review-states had findings with
  **no `visual_evidence`** (the `tests/fixtures/2026-05-02-9cd2a2ac` fixture: 0/12 +
  0/14). The current pipeline derives it per finding (`3e7bd452`: 26/26 + 25/25,
  `reason: "Derived from match_method=e_index_lookup"`). **No `visual_quality` bug** —
  upstream data, already resolved. Regression guard: `TestRealV2ShapeRegression`.
- **`acquire_url.py`:** the previously-undecided `//`→`/* */` edit was a *real* Windows
  `SyntaxError` fix (`_build_elements_js()` is collapsed to one line via
  `" ".join(source.split())`, so `//` comments swallowed the eval payload). Now on
  `main` as G27 — no longer a dangling working-tree edit.

## 4. What's open (carried)

- **§10 spec decisions** — (a) opus-by-default specialists (~+75% cost/audit, reduces
  sonnet drift); (b) Task-subagent vs Agent-teammate default for v2. Both are
  **brainstorm-first** and genuinely Dan's cost/architecture calls. Not started.
- **Backlog #3** — teammate dispatch reliability; can't fix in-repo (Claude Code
  Agent-tool level). Unchanged.
- §6 is otherwise fully cleared (G25/G28/Backlog#6/G3/G9 all done this session).

## 5. Suggested skills for the next session

| Skill | When |
|---|---|
| `verification-before-completion` | Before ANY push — verify **both** runners green (the repo invariant; unittest alone hides pytest breakage). |
| `brainstorming` | Before drafting either §10 spec decision — the fix shape isn't obvious and these are deliberate spec changes. |
| `systematic-debugging` | If a canary/pipeline behaves unexpectedly (used to close Backlog #6 this session). |
| `code-review` | If a follow-up touches the canary suite or >~200 lines. |

## 6. Conventions a fresh agent should know (delta — rest in prior handoffs)

- **`run_all_canaries` is now 8 checks** (added `lead_reflection_not_stale` #7 and
  `lead_reflection_well_formed` #8). Adding a canary bumps the count assertions in
  `test_v2_canary_checks`, `test_v2_determinism_gate` (which adds +1 structural), and
  `test_visual_quality` (×2) — update **all** of them or the suite goes red.
- **New canary fixture-safety rule:** any canary keyed on `meta.json`/review-state
  must skip pre-format engagements (absent field) so the Phase-J fixtures
  (slingmods/awdmods/9cd2a2ac) stay green. Both reflection canaries do this.
- **Two new memories on this machine** (`memory/MEMORY.md`):
  `ecp-shared-checkout-branch-collision` (§0) and
  `dan-wants-explicit-recommendations-in-questions` (always mark a recommended option
  in AskUserQuestion).
- Commit cadence + commit-and-push-to-main-for-cleanup authorization unchanged
  (prior handoff §8 / memory `project_ecp_commit_cadence`).

## 7. Working-tree state

Clean — all work committed and pushed to `origin/main` @ `853138d`. No stray branches
(the collision branch `fix/acquire-url-eval-comment` was merged + deleted, local +
remote). Gitignored per-engagement baton scratch kept on disk per Dan; the durable
`scripts/baton_v1_to_v2.py` supersedes it.

---

_End of handoff. Next agent: §0 is the one that bit us — check `git branch` before
committing on this machine. Everything else is committed, pushed, and green._
