# Handoff — 2026-05-28 observability batch

**Audience:** the next Claude (or Codex, or human) picking this branch up — most likely a different machine than the originating one. Anything not in the committed repo is captured inline. `docs/ecp/` is gitignored; the engagement evidence informing this batch is summarized below.

**Previous handoff:** [docs/handoff-2026-05-27-conformance-batch.md](handoff-2026-05-27-conformance-batch.md). Read that one first if cold-starting — it covers the G16–G20 batch and architectural framing. This doc is the *delta* on top of it.

**Session window:** 2026-05-28 morning (single multi-hour session). Originating-machine root: `C:\Users\SM - Dan\Documents\GitHub\ecp` — clone path may differ.

---

## TL;DR

One audit run (`docs/ecp/2026-05-28-e4050c0e`) surfaced three orthogonal observability failures of the §0 "untraceable-misleading" class. Two commits on `main` close them:

- **`2989336` (G22+G24)** — `audit-trace.log` counters now reconcile with on-disk artifact presence via a new sixth canary. The contract already required "increment counter on dispatch" (`contracts/dispatch-contract.md:259`) — nothing structurally enforced it. Now structurally enforced.
- **`6198c92` (G23)** — `meta.json` gains a `reflection_state: "draft" | "complete"` field with explicit-verb-only promotion (mirror of G8's `report_state`). Premature reflection writes by any agent leave the state at `draft` so the operator/canary sees at a glance whether the narrative is finalized.

**The audit deliverables from `e4050c0e` are clean per the canary verdict** (`canary-results.json` shows all five PASS). The bug was that the lead's `lead-reflection.md` claimed *"synth did not run"* against an engagement where synth had actually run and produced a clean 5-story priority path. Trust failure was *observability*, not *capability*.

`main` advances from `408263f` → `a3bb9dc` (gitignore patterns, prior session) → `b1f8ba1` (prior handoff doc) → `2989336` (G22+G24) → `6198c92` (G23).

---

## 1. Where `main` is

```
6198c92  Add reflection_state draft -> complete gate (G23)
2989336  Reconcile audit-trace.log counters with observable artifacts (G22+G24)
a3bb9dc  gitignore: per-engagement lead-recovery scratch + agent-browser b64 temps
b1f8ba1  Add handoff doc for the 2026-05-27 conformance batch
408263f  Fix element_index_match_rate >1.0 bug + quarantine mojibake fixture (G20)
```

Test runners on the latest tip:
- `pytest tests/` → **690 passed, 12 skipped, 47 subtests passed**
- `python -m unittest discover -s tests` → **512 ran, 1 skipped**

For commit-level detail, see [CHANGELOG.md](../CHANGELOG.md) — the "session 6" entry covers G22+G24+G23 end-to-end. For roadmap context, see [docs/conformance-gaps.md](conformance-gaps.md) §"Observability (2026-05-28 session 6)".

## 2. The `e4050c0e` engagement — evidence preserved here

**URL:** `https://www.slingmods.com/stinger-trailer-canam-ryker` (n=6 on this URL counting the prior handoff's n=5).
**Scope:** comprehensive, 6 clusters × 2 devices.
**Outcome per canaries:** clean. Per lead-reflection: claimed failure. The discrepancy is the diagnostic story.

### Timeline forensics (file mtimes — the engagement dir is gitignored so reproducing this requires reading mtimes from the originating-machine's working tree)

| Time | Event | Source |
|---|---|---|
| 09:00–09:08 | Acquisition + DOM preprocess + anchor candidates | Mtimes on `baton.json`, `anchor-candidates-*.json` |
| 09:13–09:14 | Desktop wave 1 lands: visual-cta, content-seo, pricing, product-media, trust-credibility (5 specialists) | `cluster-*-desktop.json` mtimes |
| **09:17** | **`lead-reflection.md` written by a rogue agent.** Claims: "5 of 6 desktop / 0 of 6 mobile / synth DID NOT RUN / ethics DID NOT RUN." Each true at 09:17 — but the pipeline keeps running. | `lead-reflection.md` mtime |
| 09:21 | Mobile wave 1: trust-credibility, visual-cta | mtimes |
| 09:27 | Mobile: content-seo, performance-ux | mtimes |
| 09:30–09:31 | Mobile: pricing, product-media + desktop: performance-ux | mtimes |
| 09:34 | **Ethics autofix fires** — 4 repairs (2 dedupes + 2 missing-`proposed_anchor` injections via the new G15 P1-3 v2 schema-valid `section_index=0, section-bottom-overlay` recipe) | `ethics-findings.repairs.json` |
| 09:35 | Ethics emission lands | `ethics-findings.json` |
| 09:36 | Canonical-frefs built (0 dropped), all 5 canaries PASS | `canary-results.json`, `canonical-frefs-dropped.json` |
| 09:36→09:57 | **Synthesizer runs (~21 min)** | `audit-desktop.md`, `audit-mobile.md` mtimes |
| 09:58 | Render: visual reports + editor | mtimes |
| 09:59 | `meta.json` → `engagement_status: complete` | `meta.json` |

**Lead-reflection was written at 09:17, never updated. Pipeline completed cleanly at 09:59.** Reflection content went stale 42 minutes later but was the only operator-facing narrative.

### Where the contracts failed at observability

| Bug | Spec said | Reality | What G## closed |
|---|---|---|---|
| `audit-trace.log` counters all 0 despite 12 specialists + 1 ethics + 1 synth + 2 acquirers landing | `contracts/dispatch-contract.md:259` says lead MUST increment counter after every dispatch | Lead never incremented. Structural self-check in `contracts/trace-assertion-canary.md` defined but not enforced | **G22+G24** new canary structurally enforces |
| `lead-reflection.md` written prematurely by rogue specialist agent; never refreshed | `contracts/lead-discipline.md` makes lead-reflection the canonical postmortem | No state machine distinguishing "draft narrative" from "final attestation" — anyone could write authoritatively | **G23** mirrors G8's `report_state` machine for `reflection_state` |
| Five substantive canaries all PASS, deliverable looked clean, but operator-facing narrative said "we failed" | §0 "never untraceable, never silently misleading" demands narrative match reality | No reconciliation between trace counters and observed artifacts | **G24's canary** is exactly that reconciliation |

### Per-artifact verdict in `e4050c0e`

- **Trace counters** (`audit-trace.log`, 506 bytes total — only the header block): `subagent_spawned_acquirers: 0`, `team_spawned_specialists: 0`, `subagent_spawned_ethics: 0`, `subagent_spawned_synthesizer: 0`. **G22+G24 would now FAIL loudly** with each under-counted role named.
- **`canonical-frefs-dropped.json`:** `{"dropped_count": 0, "dropped": []}` — clean. G16 happy.
- **`ethics-findings.repairs.json`:** 4 repairs (G15 P1-3 v2 working as designed).
- **`canary-results.json`:** all 5 PASS. `element_index_match_rate: 0.957 (22/23)` (G20 invariant intact — no impossible >1.0).
- **`synthesizer-emission-v1.json`** (38800 bytes): real, with 5 priority-path stories. `priority_path_count_parity` canary confirms desktop=5/5, mobile=5/5.
- **`lead-reflection.md`** (the only broken artifact at audit-end): stale, never refreshed, claims pipeline did not complete.

### Real ethics findings in this run (for n=6 ethics-variance tracking)

| Role | Count | Notes |
|---|---|---|
| CLEAR | 6 | Standard slingmods baseline |
| ADJACENT | 1 | `priceValidUntil` rolling-date pattern — same surface Run B + C flagged. The page now reads `priceValidUntil: 2026-05-29`, captured 2026-05-28 → still rolling forward daily, confirms the prior runs' suspicion |
| BLOCK | 0 | None |

(Per the prior handoff's n=5 table: A=0/9, B=2/5, C=2/4, D-6=mix, D-10=2-actionable, F=3/7. E4050c0e is now part of the n=6 baseline at 1/6.)

## 3. What closed this session (in commit order)

### `2989336` — G22+G24 (reconciliation canary)
- New `check_trace_counters_reconcile_with_artifacts` in `scripts/assembly/canary_checks.py` walks the filesystem and asserts `trace_counter >= observed_artifact_count` per role (acquirers, specialists, ethics, synthesizer, cluster_files_written).
- v1/v2 counter-name aliases (`team_spawned_auditors`/`team_spawned_specialists`, `team_spawned_acquirers`/`subagent_spawned_acquirers`) accepted per `contracts/dispatch-contract.md` §"Backwards compatibility" — canary takes `max(alias_values)`.
- Wired as canary #6 in `run_all_canaries`. Existing count-asserting tests (`test_v2_canary_checks.py`, `test_v2_determinism_gate.py`, `test_visual_quality.py`) bumped 5→6 (and the determinism gate 6→7 incl. structural).
- 8 new regression tests in [tests/test_g24_trace_counters_reconcile.py](../tests/test_g24_trace_counters_reconcile.py), including a literal reproducer of the `e4050c0e` all-zero-counters shape.
- **G22 is closed *de facto* by G24's enforcement** — the contract-discipline rule existed; only enforcement was missing.

### `6198c92` — G23 (`reflection_state` gate)
- New `scripts/assembly/reflection_state.py` mirrors `scripts/assembly/report_state.py` (G8's draft → client-verified machine) — same shape, different field name and exception class.
- `meta.json` gains `reflection_state: "draft" | "complete"` documented in [contracts/meta-schema.md](../contracts/meta-schema.md) and enum-checked in `scripts/assembly/meta_validator.py`. Missing/null/unknown reads as `draft`.
- New CLI verb `generate-report.py --mark-reflection-complete` is the lead's attestation. Refuses under `--auto` with `AutoCompletionError` (subclasses `PermissionError`, parallel to G8's `AutoPromotionError`).
- [skills/audit/SKILL.md](../skills/audit/SKILL.md) step 15 + Exit Criteria instruct the lead to invoke the verb at completion.
- 11 unittest-style regression tests in [tests/test_g23_reflection_state_gate.py](../tests/test_g23_reflection_state_gate.py), including a load-bearing entanglement check that flipping `reflection_state` doesn't touch `report_state`.

## 4. Conversational context that informed this session (not in any commit)

These came up in discussion and shaped decisions but aren't in the code yet. Capturing here for continuity:

### G21 candidate — frozen Cursor agents leak into Claude Code Agent discovery (NOT committed)

While picking the dispatch mode for `e4050c0e`, the audit lead in Claude Code prompted Dan with three options including *"Delegate to ecp-orchestrator (Recommended)"*. Investigation:
- `agents/ecp-orchestrator.md` exists from the migration commit (`e245ddf`), explicitly says *"You are the orchestrator for E-Commerce Psychology in Cursor (not Claude Code)"*.
- `product.md` §8: *"Codex (and Cursor) are archived, not shipped. […] Reserved seams: re-portable from the archive if ever wanted, but not part of the canonical product."*
- Zero references to `ecp-orchestrator` in `skills/`, `contracts/`, or `workflows/` — the canonical SKILL never wires it in.
- But Claude Code's Agent tool auto-discovers `agents/*.md`, so the lead inferred a delegation path from the file's *presence*, not from the spec.

**Dan's key insight:** *"the orchestrator was always lead just by a different name"* — the role is the same, the runtime differs. Opus 4.7 read the agent's NAME literally (treating "orchestrator" as a distinct role) when it should have read the role abstractly. This is a structural failure of `product.md` §5's "frozen scope" — the spec freezes a concept but the *discoverable surface* leaks.

**Proposed G21 fix** (not yet committed — write it up + propose for the next session):
1. Move `agents/*.md` out of plugin-discovery scope (either delete per §5 freeze, or relocate to `archive/cursor-agents/`).
2. Add 5-line docstring at top of `scripts/cursor_bootstrap_url.py` clarifying it's the canonical deterministic acquirer despite the Cursor-flavored name (which generalized post-migration).
3. One-line addition to the SKILL's checkpoint prompt: explicitly state delegation is via Task subagent to the current SKILL, NOT to `agents/*.md` files.

This is a **fourth instance of the "freeze-as-invariant test failing in practice" pattern** (alongside G16, G17, and the G22+G24 batch): spec freezes a concept but the discoverable surface stays available. Same lesson — to freeze something operationally, *delete the surface*, don't just mark it "out of scope" in docs.

### Wave-throttle architectural challenge (Dan's pushback)

When discussing the G17 Layer B wave-throttle (`waves of ≤5`), Dan raised a real architectural point: **the team-mailbox affordance is the primary reason teammates exist vs. independent Task subagents; serializing waves breaks the mailbox model.** Per `contracts/dispatch-contract.md:88`:

> *"v2 specialists do NOT SendMessage anyone, do NOT broadcast intent, do NOT propagate SYNTHESIS_HINT. […] The teammate dispatch shape is a transport choice, not a coordination requirement."*

So *for v2 specifically* the team-mailbox is already disabled. Which raises the deeper question Dan flagged: **why are v2 cluster specialists still Agent teammates instead of Task subagents?** The architecture is being kept for *forward-compatibility with v2.1* that might re-introduce peer messaging, not for current v2 capability.

**The Amazon engagement (`0669899d` from session 5) empirically proved Task subagent dispatch works fine for v2 specialists** — when teammates didn't auto-execute (4 of 12 only), the lead switched to Task and 100% succeeded. So the answer to "should v2 cluster specialists be Task subagents by default?" is plausibly *yes* — but that's a `product.md` §9 / §10 Spec Change Log call. **Not in scope for this session; flagging as architectural question for a future session to weigh deliberately.**

### Opus-by-default for cluster specialists (Dan's instinct)

Dan suggested mid-run: *"we start using opus subagents instead of sonnet."* Honest take per `product.md` §0:

- Many session-5 patches (G15 P1-3 autofix, G19 substantive-quote filter, `cec2794` jurisdiction steer) *compensate for sonnet prompt-drift*. Opus would reduce the need for them at the source.
- The lead is already opus and the synthesizer is already opus — precedent: where the trust contract is most exposed, use the stronger model. Specialists are equally trust-exposed (they author the cited findings).
- Cost: ~+75% per audit (~$11 → ~$54 specialist budget); wall-clock: ~+50% (+6-12 min on a 6-cluster × 2-device run). **Material but not material relative to the cost-of-a-wrong-finding for a deliverable shipped under Dan's professional name.**

This needs to be a deliberate `product.md` §9 / §10 Spec Change Log entry. The cleanest shape:
1. Default specialist model: **opus** (was sonnet).
2. Add `--quick` flag for the old sonnet behavior (mirrors the existing `--deep` escalation, just inverted).
3. Validate empirically — next opus-specialist run should show autofix repair-count drop materially.

**Not in scope for this session; flagging as Spec Change Log candidate.**

## 5. What's open

| # | Item | Status | Notes |
|---|---|---|---|
| **G21** | Frozen Cursor agents leak into Claude Code Agent discovery | **Drafted in this handoff §4; NOT committed.** | Three concrete edits proposed; 30-min mechanical cleanup commit |
| Backlog #3 (carried from session 5) | Teammate-vs-Task subagent dispatch reliability | Cannot fix in this repo — needs Claude Code Agent-tool diagnosis | Dan's session-6 architectural pushback strengthens the case for *switching v2 specialists to Task by default*; needs §10 Spec Change Log entry |
| Backlog #6 (carried from session 5) | `visual_quality` canary returning all-zeros on v2 emissions | Needs a live run to verify a fix; defer until clean v2 review-state fixture exists | Unchanged |
| Path sweep (task from session 5) | `${CLAUDE_PLUGIN_ROOT}` mechanical rewrite of bare relative refs in subagent-facing templates | Deferred per session-5 scope analysis | Unchanged |
| Opus-by-default for cluster specialists | Dan-flagged direction, aligned with §0 | NOT committed; needs §10 Spec Change Log entry | Cleanest shape: flip default + add `--quick` flag |
| Lead-reflection-stale canary | When `phase: complete` but `reflection_state: draft`, flag it | Possible follow-up canary; G23 sets up the state machine but doesn't add the consumer-side check | One-line addition to `run_all_canaries` if useful |
| G3 (P3, from session 5) | DOM-present-but-not-displayed canary for absence findings | Optional hardening | Unchanged |
| G9 (P3, from session 5) | ISN'T-list copy spot-check | Cosmetic | Unchanged |

## 6. What the next live audit will exercise (delta from prior handoff)

Everything from the prior handoff §5 still applies (G16 / G17 / G18 / G19 / G20 / G15 P1-3 v2 / etc.). New for this session:

| New behavior | Where to look |
|---|---|
| **Sixth canary: `trace_counters_reconcile_with_artifacts`** | `canary-results.json` → 6 entries (was 5). PASS line: `acquirers=2/2, specialists=12/12, ethics=1/1, synthesizer=1/1`. If FAIL: each under-counted role named in the summary |
| **Audit-trace counter discipline now enforced via above** | Lead is now structurally required to increment counters after each dispatch — `team_spawned_specialists: N` must match observed `cluster-*-*.json` count |
| **`meta.json` has `reflection_state` field** | Default `draft`. The lead must explicitly invoke `generate-report.py --mark-reflection-complete` at audit end (SKILL step 15) to flip it to `complete` |
| **CLI verb `--mark-reflection-complete`** | Operator can also invoke directly. Refuses under `--auto` with exit 2 + `AutoCompletionError` naming "premature finalization" |
| **`meta_validator.py` enum check on `reflection_state`** | Invalid values (anything other than `draft`/`complete`) produce a warning, not a hard fail |

## 7. The single highest-leverage thing the next agent can do

**Read this handoff doc + [docs/handoff-2026-05-27-conformance-batch.md](handoff-2026-05-27-conformance-batch.md), then read [docs/conformance-gaps.md](conformance-gaps.md). Then wait for Dan to fire `/ecp:audit`.** The session-5 lesson about "every confident pre-data hypothesis got corrected by the next data point" still holds — the session-6 `e4050c0e` analysis is the clearest example (Dan reported "synth wasn't spawned correctly" based on the lead-reflection; investigation showed synth actually ran fine and the lead's narrative was wrong).

**Evidence first, then fixes.** Don't speculate about what the next live run will surface; let it surface.

If Dan asks for proactive work before the live run, the highest-value candidate this session is **G21 (frozen Cursor agents cleanup)** — it's 30 minutes of mechanical cleanup with clear scope, doesn't need a live run to validate, and closes a real surface leak. Second-highest is **drafting the §10 Spec Change Log entries for (a) opus-by-default specialists and (b) v2 specialists as Task subagents by default** — those are the architectural calls Dan raised that need writeup before they're executable. Both are good "between-runs" candidates.

## 8. Where to find things in the repo (delta from prior handoff)

Everything in the prior handoff §8 still applies. New for this session:

| What | Where |
|---|---|
| Reflection state machine module | [scripts/assembly/reflection_state.py](../scripts/assembly/reflection_state.py) |
| Trace-counter reconciliation canary | [scripts/assembly/canary_checks.py](../scripts/assembly/canary_checks.py) — `check_trace_counters_reconcile_with_artifacts` |
| Meta-schema docs (incl. new `reflection_state` row + valid-values section) | [contracts/meta-schema.md](../contracts/meta-schema.md) |
| Meta validator enum check | [scripts/assembly/meta_validator.py](../scripts/assembly/meta_validator.py) |
| `--mark-reflection-complete` CLI verb wiring | [scripts/generate-report.py](../scripts/generate-report.py) |
| New regression tests | [tests/test_g23_reflection_state_gate.py](../tests/test_g23_reflection_state_gate.py), [tests/test_g24_trace_counters_reconcile.py](../tests/test_g24_trace_counters_reconcile.py) |

## 9. Working-tree state on the originating machine (NOT committed, NOT mine to commit)

Same pattern as last handoff §7. As of this writing:

```
M  --quality                                              (pre-existing binary mod, unrelated)
?? scripts/one_off/convert_b0051311_batons.py             (Run A French-recovery converter — Dan's call)
?? scripts/trim_batons_phase5.py                          (NEW — e4050c0e per-engagement helper)
```

**`scripts/trim_batons_phase5.py` is new since the prior handoff** and matches the same per-engagement lead-recovery pattern that the session-5 `.gitignore` covers for `_write_*`, `write_*`, `temp_*`, `run_*`. The gitignore could be extended with `scripts/trim_*.py` to suppress this whole pattern going forward — but `scripts/one_off/trim_r03_batons.py` IS tracked, so extending the pattern to `scripts/trim_*.py` (top-level only, NOT `scripts/one_off/trim_*`) would be the correct narrowing. **Not extended in this commit** because it's per-Dan-decision the same way the original session-5 `.gitignore` work was scoped.

**Do not commit these scratch files** on a cross-machine handoff continuation. Per the same logic as last handoff §7, they're engagement-specific, not reusable.

## 10. Test coverage added this session

| File | Covers | Count |
|---|---|---|
| [tests/test_g24_trace_counters_reconcile.py](../tests/test_g24_trace_counters_reconcile.py) | Trace-counter ≥ observed artifact reconciliation, v1 alias acceptance, over-count tolerance, `e4050c0e` literal reproducer, partial-violation granular naming, skip-safe paths, parser tolerance against prose | 8 |
| [tests/test_g23_reflection_state_gate.py](../tests/test_g23_reflection_state_gate.py) | `reflection_state` draft-by-default, valid-values round-trip, `set_reflection_complete` atomicity + `AutoCompletionError` refusal under `--auto`, CLI verb exit codes, G8/G23 entanglement-prevention check | 11 |

Plus updates to existing count-asserting tests (`test_v2_canary_checks.py`, `test_v2_determinism_gate.py`, `test_visual_quality.py`) — `5→6` and `6→7` increments mirroring the G16 commit pattern.

## 11. Suggested skills for the next session

(Carried from prior handoff §11 — unchanged.)

| Skill | When |
|---|---|
| `verify` | After Dan fires the next `/ecp:audit`, before claiming "the new canaries work" — actually inspect the engagement dir for the new outputs (canonical-frefs-dropped, [G16] stderr, autofix repairs log, **`reflection_state` in `meta.json`, sixth `trace_counters_reconcile` canary line**) |
| `verification-before-completion` | Before pushing any post-handoff commit, run `pytest tests/` + `python -m unittest discover -s tests` and confirm both green |
| `using-superpowers` | At session start (always the first thing) |
| `code-review` | If a follow-up commit touches more than ~200 lines or modifies the canary suite |
| `brainstorming` | If a new architectural question surfaces (e.g. opus-by-default Spec Change Log, agents/* cleanup scoping) and the fix shape isn't obvious |

NOT suggested:
- `tdd` — overkill for the small surgical fixes remaining
- `frontend-design` and design skills — out of scope

## 12. Open questions Dan flagged that have no committed answer yet

These are *questions*, not work items. The handoff doc captures them so the next agent doesn't re-discover them from cold:

1. **Should v2 cluster specialists be Task subagents by default?** The architecture-of-record says teammates because of the team-mailbox affordance, but v2 explicitly opts out of mailbox use. Amazon engagement empirically proved Task transport works for v2.
2. **Should opus be the default cluster specialist model?** Cost +75%/audit, but many recent patches compensate for sonnet drift. §0 argues yes.
3. **Where should the `agents/` dir live structurally?** Currently auto-discovered by Claude Code; explicitly Cursor-targeted per the file docstrings; archived per `product.md` §8. G21 candidate.
4. **The lead's `lead-reflection.md` premature-write problem** — Dan's read identifies a `specialist-content-seo-desktop` agent as the writer. That's a scope violation independent of G23: a specialist shouldn't be writing the lead's file at all. G23 closes the *narrative trust* surface; a separate fix would close the *scope violation* surface (e.g., file-ownership check in `atomic_write` or contract-level prohibition in `specialist-prompt-v2.md`).

---

_End of handoff. If you're reading this and Dan has already fired the next audit, start by checking the engagement dir for: (a) `canary-results.json` containing 6 entries with `trace_counters_reconcile_with_artifacts` PASS, (b) `meta.json` `reflection_state: "complete"` (lead invoked the verb) or `"draft"` (lead skipped — that's a discipline gap worth noting). Both signals are new to this session._
