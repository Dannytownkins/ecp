# Handoff — 2026-05-27 conformance batch

**Audience:** the next Claude (or Codex, or human) picking this branch up — possibly on a different machine than the one the session ran on. Anything they need that's NOT in the committed repo is captured inline here. `docs/ecp/` (the engagement dirs) **is gitignored**; everything referenced from there is summarized below.

**Session window:** 2026-05-27 (single multi-hour session). **Project root:** `C:\Users\SM - Dan\Documents\GitHub\ecp` on the originating machine; clone path may differ.

---

## TL;DR

Ten commits landed on `main` (`fd3307c..408263f`), all backed by regression tests, both runners green throughout. Closed: G16, G18, G10, G15 P1-3 (+ v2 fix), G16 Layer 3, G2, G17, G19, G20. Three open items remain — only one is a real engineering gap (`#3` teammate dispatch); the other two need a live audit run to make progress. **The next move is for Dan to fire `/ecp:audit`** on any product page; that run will exercise every new canary and surface whether the fixes hold under real load.

---

## 1. Where `main` is

```
408263f  Fix element_index_match_rate >1.0 bug + quarantine mojibake fixture (G20)
8e764f4  Stop baton_precedence_verbatim_anchor false-positives (G19)
75fd5e0  Acquirer contamination guard + fan-out throttle (G17)
84cd4a4  Fix emission_autofix injecting schema-invalid proposed_anchor (G15 P1-3 v2)
0c223f4  G2 citation re-audit: 3 of 4 flagged citations verified to source
6b40230  Consolidate cluster-emission validator to single shared instance (G16 Layer 3)
e7f6af5  Add ethics-emission pre-validation autofix (G15 P1-3)
2fcdc89  Scrub inert docs/plans provenance refs (G10)
34e67b1  Harden drift-gate why-slice terminator against trailing sections (G18)
00b1e23  Surface canonical-view silent drops + add clusters_represented canary (G16)
fd3307c  (prior session HEAD — docs: record G1/G15 prompt steers)
```

All 10 commits are on `origin/main`. Test runners on the latest tip:

- `pytest tests/` → **783 passed, 12 skipped, 0 failed, 38 subtests**
- `python -m unittest discover -s tests` → **493 run, 1 skipped, 0 failed**

For commit-level detail, see [CHANGELOG.md](../CHANGELOG.md) — the "session 4" and "session 5" sections cover this batch end-to-end.

## 2. Conformance roadmap status

The canonical roadmap is [docs/conformance-gaps.md](conformance-gaps.md). Quick orientation for someone landing cold:

**Closed this session (in commit order — search `git log -S 'G##'` for each):**
- **G16** (`00b1e23`) — `build_canonical_view` silent drops + `clusters_represented` canary
- **G18** (`34e67b1`) — drift-gate why-slice terminator absorbs trailing `## Methodology Notes`
- **G10** (`2fcdc89`) — scrub inert `docs/plans/…` provenance comments (17 files)
- **G15 P1-3** (`e7f6af5`) — ethics-emission pre-validation autofix (4 repair classes)
- **G16 Layer 3** (`6b40230`) — consolidate two duplicate validators to one shared instance
- **G2** (`0c223f4`) — citation/legal re-audit; 3/4 flagged items verified via `WebFetch`
- **G15 P1-3 v2** (`84cd4a4`) — fix autofix injecting schema-invalid `proposed_anchor`
- **G17** (`75fd5e0`) — cross-engagement session contamination guard + fan-out throttle
- **G19** (`8e764f4`) — `baton_precedence_verbatim_anchor` false-positives stopped
- **G20** (`408263f`) — `element_index_match_rate` impossible-rate bug + Amazon mojibake quarantine

**Still open (priority-ordered):**
1. **Backlog item #3** — teammate-vs-subagent dispatch reliability. Across n=5, the `Agent` teammate transport had intermittent auto-execute failures (Amazon engagement: 4 of 12 teammates auto-executed; the lead re-dispatched the remaining 8 as `Task` subagents successfully). The runtime contract (`contracts/dispatch-contract.md`) explicitly permits the transport swap, but the underlying reliability question is real. **Cannot be fixed in this repo** — needs Claude Code-level diagnosis of why teammate spawns don't auto-execute prompts. Possibly an environmental issue (rate limits, MCP transport, Claude Code version). The wave-throttle (G17 Layer B) reduces the surface area for this.
2. **Backlog item #6** — `visual_quality` canary returns all-zeros on v2 emissions in Run D (`4a0721e9`). Read/write mismatch — the reader was probably wired to v1 synthesizer shape. **Needs a live run** to produce a clean v2 review-state fixture before the fix can be verified; touching the canary without that risks shipping a different broken thing.
3. **Task 8 — `${CLAUDE_PLUGIN_ROOT}` path sweep.** Originally scoped as a 24-file mechanical sweep of 267 bare path refs. Audit showed most refs are markdown links (`[text](relative.md)`) or schema/code-name tokens, not "Read X" instructions — a mechanical sweep would convert false positives. Re-scoped as: targeted fix of only the truly imperative `Read \`(contracts|workflows|references|schema)/X\`` patterns in subagent-facing templates (`specialist-prompt-v2.md`, `synthesizer-v2.md`, `ethics-subagent-v2.md`). The runtime works today — leads inject preambles per-spawn to compensate. Defer to a session that can scope it carefully; not blocking.
4. **G3 (P3)** — `DOM-present-but-not-displayed` canary for absence findings without screenshot-region anchors. Optional hardening.
5. **G9 (P3)** — ISN'T-list copy spot-check in report templates + ethics-gate copy. Cosmetic.

## 3. The n=5 audit batch — evidence preserved here because engagement dirs are gitignored

Six audits ran during this session (one URL appears five times for n=5; one Amazon audit). **All engagement dirs are gitignored** (`.gitignore:19 docs/ecp/`). The evidence informing every gap in this batch lives in lead-reflection files in those dirs. The key telemetry per engagement is captured below; full lead-reflection prose is in the originating machine's working tree.

URL for the 5-run series: `https://www.slingmods.com/stinger-trailer-canam-ryker` (OpenCart, $4,399 product page).

| ID | Scope | Devices | Clusters | Outcome highlights |
|---|---|---|---|---|
| **2026-05-27-b0051311** | comprehensive | desktop + mobile | 6 (CRO) | **Run A.** French→English synthesizer detour (lead misread `"french."` as a language); recovered via `_build_synth.py` glue. 2 ethics retries (path-form telemetry, missing `proposed_anchor` on absent, dup tuple). Foundational data for G15 P1-3. |
| **2026-05-27-af72a2ae** | comprehensive | desktop + mobile | 6 (CRO) | **Run B.** Clean run baseline. Ethics: 2 ADJACENT (`priceValidUntil` rolling-date, mobile Omnisend popup) + 5 CLEAR. `element_index_match_rate = 1.000 (41/41)`. Drift-gate false-positive on F-33 from per-device methodology section → G18 reproducer. |
| **2026-05-27-52f53a53** | comprehensive | desktop + mobile | 6 (CRO) | **Run C.** **G16 root-cause engagement.** 6 of 12 cluster files silently dropped by `build_canonical_view`'s `except: continue` (template_id, expected_overlay, reason-too-long, missing proposed_anchor); 25 high-severity FAIL findings vanished from the report with all canaries PASS. Ethics: 2 ADJACENT (PayPal TILA, empty stars). |
| **2026-05-27-625832a6** | comprehensive | desktop + mobile | 6 (CRO) | **Run D-6.** Post-G16 commit. **Reported `element_index_match_rate=1.23` — the G20 reproducer.** Ethics: 9 findings (mix unspecified in trace). 13-way fan-out hit rate-limit → G17 Layer B evidence. |
| **2026-05-27-4a0721e9** | everything | desktop + mobile | **10 (all)** | **Run D-10.** First-of-kind full-breadth run. **G17 Layer A reproducer:** mobile acquirer captured 51 Amazon "Sponsored / Nordic Naturals" elements because the headless session drifted to amazon.com mid-extraction (a concurrent Amazon audit was navigating there). Caught by ethics + content-seo specialists independently flagging "elements look like Amazon"; recovered via `mobilefix` re-acquisition. `clusters_represented` canary fired at 10/10 (first real test at full breadth). |
| **2026-05-27-0669899d** | comprehensive | desktop + mobile | 6 (CRO) | **Amazon engagement** (`amazon.com/dp/B002CQU54Q`, Nordic Naturals Omega). Teammate dispatch unreliable (4 of 12 auto-executed; 8 re-dispatched as Task subagents). Five emission shape repairs. `baton_precedence_verbatim_anchor` false-positive on `fetchpriority="high"` → G19 reproducer #1. `element_index_match_rate = 0.762` (below 0.80 soft threshold; Amazon's DOM is messier). UTF-8 mojibake in `ethics-findings.json` → G20 quarantine. |

### Ethics variance across the five slingmods runs (informational, not actionable)

| Run | CLEAR | ADJACENT | BLOCK | Notable surfaces |
|---|---|---|---|---|
| A (b0051311) | 9 | 0 | 0 | French-detour run; over-CLEAR likely upstream noise |
| B (af72a2ae) | 5 | 2 | 0 | `priceValidUntil` rolling-date; mobile Omnisend popup |
| C (52f53a53) | 4 | 2 | 0 | PayPal TILA (false positive per Dan); empty-stars (valid per Dan); 6 clusters silently dropped |
| D-6 (625832a6) | mix | mix | 0 | 9 findings total |
| D-10 (4a0721e9) | mix | 2 actionable | 0 | Survived Amazon contamination after recovery |

The non-determinism is real but `product.md` §4.1's "adjacent class is a feature, operator filters" model handles it gracefully. **Do NOT chase ethics-determinism as a P1 gap** — earlier in the session we considered rebalancing the `cec2794` jurisdiction steer, but n=3 data showed the steer wasn't broken (Run B produced valid adjacents naturally). Variance ≠ broken.

## 4. Architectural model refresher (in case you're cold-loading)

`product.md` is the constitution. Read it first if you haven't. The trust contract has two layers with **opposite recall/precision priorities** for adjacents vs. hotspots:

- **§4.1 content trust:** prefers **recall > precision** for the `Adjacent` ethics class. Surface borderline patterns so the operator can verify; over-flagging is cheap to delete, under-flagging silently misleads. Dan's words: *"I'd rather surface and me delete from the final report vs. not having the information to look up on my own."*
- **§4.2 presentation trust:** prefers **precision > recall** for hotspots. Auto-place only at ~99.9% confidence; below threshold leave blank. A wrong hotspot is visually embedded and worse than a missing one.

This asymmetry is intentional and shows up in several closed gaps: G4 leaves hotspots blank below threshold (precision); the autofix injects a `proposed_anchor` on absent findings rather than dropping them (recall).

**Operational trust** (§0 "never untraceable, never silently misleading") was the headline insight of this session. G16 + G17 are both *operational* failures (silent drops + session contamination), not content/presentation failures. The conformance-gaps doc now has a "Concurrent-audit robustness" section alongside "Trust integrity" to reflect that operational and content trust are equally first-class.

## 5. What the next live audit will exercise

When Dan runs `/ecp:audit <url>`:

| New behavior | Surface |
|---|---|
| **Specialist dispatch in waves of ≤5** | Lead waits on per-wave file-presence before next wave. Slower-feeling first phase but no rate-limit storms. Per `contracts/dispatch-contract.md` §"Why cluster specialists keep teammate status" point 1. |
| **`[G16]` stderr** if any cluster file fails canonical-view validation | `lead_prep.py build-canonical-frefs` writes `canonical-frefs-dropped.json` always (empty list = clean) + exits code 4 on any drops. Phase-blocks the audit. |
| **`clusters_represented` canary** (#5 in `run_all_canaries`) | Hard-fails if any requested CRO cluster has zero canonical refs OR if drops file is non-empty. |
| **`[autofix]` stdout** if autofix ran on any emission | `test-specialist.py autofix --in-place` is the lead's pre-validate step per `skills/audit/SKILL.md` Validation step 1. Repair log at `<emission>.repairs.json`. |
| **Schema-valid `proposed_anchor` injection** on absent ethics findings | No more hand-normalization of `above-fold-banner`/`both` invalid enums. The injected default is `{kind: section, section_index: 0, placement: section-bottom-overlay, viewport: <derived from finding.device>}`. |
| **Acquirer contamination guard** in `cursor_bootstrap_url.py` | Only fires on real cross-engagement session drift. Loud STATUS line + exit 1 if `window.location.hostname` doesn't match the validated baseline at any per-section extraction call. |
| **Drift-gate why-slice** terminates at any `##/###/####` boundary | No more false-positive drift on the last finding when synthesizer writes a trailing `## Methodology Notes` section. |
| **`element_index_match_rate`** bounded by [0, 1.0] | Run D-6 had reported `1.23`; that's mathematically impossible now. |
| **`baton_precedence_verbatim_anchor`** no longer false-fires | Attribute literals (`fetchpriority="high"`) and short generic words (`"Search"`) are excluded from the matcher. |

## 6. The next live audit's two highest-value outcomes to watch for

1. **Does any new canary fire `FAIL`?** If `clusters_represented` flips to FAIL, you've reproduced the G16 root cause in a controlled setting — capture which clusters dropped and which schema rule they violated, that's the input for G16 Layer 4 (the canonical schema reconciliation Layer 3 deferred for non-urgency).
2. **Does the autofix's repairs log show repeated patterns?** If a specific repair fires across multiple emissions every run, that's a candidate for tightening the specialist prompt to emit valid shapes in the first place — a more durable fix than autofix-after-the-fact. Per `scripts/assembly/emission_autofix.py` docstring, the deferred autofix expansions include: enum coercion for `change_type`/`change_scope`, anchor-candidate registry reconciliation, and additional-property strip for `template_id`/`expected_overlay`.

## 7. Working-tree state on the originating machine (NOT committed, NOT mine to commit)

These are Dan's per-engagement lead-recovery scratch files; they're untracked because `docs/ecp/` is gitignored and per-run scratch like this doesn't belong in repo. Listed here so a fresh agent on a different machine knows they exist and what they are:

```
M  --quality                                              (pre-existing binary mod, unrelated)
?? C:UsersSM-DanAppDataLocalTempelem_b64.txt              (agent-browser eval temp)
?? C:WindowsTempel_js_b64.txt                             (agent-browser eval temp)
?? scripts/_write_visual_cta_desktop.py                   (Run lead emergency-write helper)
?? scripts/assembly/_write_perf_ux_desktop.py             (Run lead emergency-write helper)
?? scripts/assembly/write_checkout_flows.py               (Run lead emergency-write helper)
?? scripts/assembly/write_visual_cta_desktop.py           (Run lead emergency-write helper)
?? scripts/one_off/convert_b0051311_batons.py             (Run A French-recovery converter)
?? scripts/run_cat_nav_mobile.py                          (Run D-10 recovery helper)
?? scripts/temp_post_purchase_write.py                    (Run D-10 recovery helper)
?? scripts/write_ethics.py                                (per-engagement ethics-emission helper)
```

**Do not commit these** as part of any handoff continuation. They're per-engagement, not reusable, and Dan would need to write fresh ones for any future recovery anyway. If anything, the *patterns* they represent should be lifted into canonical helpers (e.g., a generic emission-rewrite utility) rather than these specific scripts being normalized into the repo.

The **stale local branches** that should be deletable post-merge:
```
backlog-validator-tightening    (merged in 8e764f4)
fix-canary-math-and-mojibake    (merged in 408263f)
g19-canonical-view-silent-drops (merged in 00b1e23)
harden-acquirer-and-fanout      (merged in 75fd5e0)
```

All four exist on `origin/` too — clean up at your leisure with `git branch -d <name> && git push origin --delete <name>`. Not urgent; branches are ephemeral metadata.

## 8. Where to find things in the repo

| What | Where |
|---|---|
| Product constitution | [product.md](../product.md) |
| Conformance roadmap (the single source of truth on what's open/closed) | [docs/conformance-gaps.md](conformance-gaps.md) |
| Per-commit changelog | [CHANGELOG.md](../CHANGELOG.md) |
| Audit SKILL (the lead's entry-point prompt) | [skills/audit/SKILL.md](../skills/audit/SKILL.md) |
| Acquisition workflow | [workflows/acquire.md](../workflows/acquire.md) |
| Dispatch contract (teammates vs Task; wave-throttle rule) | [contracts/dispatch-contract.md](../contracts/dispatch-contract.md) |
| Ethics subagent prompt (jurisdiction-matching) | [contracts/ethics-subagent-v2.md](../contracts/ethics-subagent-v2.md) |
| Specialist subagent prompt template | [contracts/specialist-prompt-v2.md](../contracts/specialist-prompt-v2.md) |
| Synthesizer prompt template | [contracts/synthesizer-v2.md](../contracts/synthesizer-v2.md) |
| Canary checks (incl. new `clusters_represented` #5) | [scripts/assembly/canary_checks.py](../scripts/assembly/canary_checks.py) |
| Emission autofix module (G15 P1-3) | [scripts/assembly/emission_autofix.py](../scripts/assembly/emission_autofix.py) |
| Validator (the single shared instance per G16 L3) | [scripts/assembly/json_parser.py](../scripts/assembly/json_parser.py) — `get_validator()` |
| Canonical-view builder (G16: returns 3-tuple with drops) | [scripts/report/v2_loader.py](../scripts/report/v2_loader.py) — `build_canonical_view` |
| Acquirer with contamination guard (G17) | [scripts/cursor_bootstrap_url.py](../scripts/cursor_bootstrap_url.py) — `_build_elements_js` + `_check_for_contamination` |
| Lead-prep CLI (G16: writes `canonical-frefs-dropped.json`, exits 4) | [scripts/lead_prep.py](../scripts/lead_prep.py) — `build_canonical_frefs` |
| Drift-check (G18: extended terminator regex) | [scripts/assembly/synth_input.py](../scripts/assembly/synth_input.py) — `extract_finding_prose` |

## 9. Test coverage added this session

Five new test files. Total: 30+ new regression tests across G16, G18, G15, G17, G19, G20:

| File | Covers |
|---|---|
| [tests/test_g16_canonical_view_surfaces_drops.py](../tests/test_g16_canonical_view_surfaces_drops.py) | 3-tuple contract, dropped-emissions content, lead_prep CLI exit codes |
| [tests/test_g16_clusters_represented_canary.py](../tests/test_g16_clusters_represented_canary.py) | All pass / fail / skip cases of the new canary |
| [tests/test_g16_layer3_single_validator.py](../tests/test_g16_layer3_single_validator.py) | `assertIs` identity check that `test-specialist.py` and `json_parser.py` share one validator instance |
| [tests/test_g15_emission_autofix.py](../tests/test_g15_emission_autofix.py) | All 4 repair classes, idempotency, immutability, schema-validity-against-real-validator |
| [tests/test_acquirer_contamination_guard.py](../tests/test_acquirer_contamination_guard.py) | Hostname inlining + JSON-escape safety + sentinel detection + constant-removal lock |

Plus targeted additions to existing test files:
- `tests/test_v2_synth_input.py::TestG18WhySliceTerminatorHardening` (3 tests)
- `tests/test_v2_business_rules.py::TestG19BatonPrecedenceFalsePositiveFixes` (4 tests)
- `tests/test_v2_canary_checks.py::test_g20_absent_lines_with_at_eN_in_proposed_anchor_do_not_inflate_rate` (1 test)
- `tests/test_no_mojibake_in_fixtures.py` — Amazon engagement added to `KNOWN_BROKEN_EVIDENCE_DIRS`

## 10. Conventions a fresh agent should know

These weren't all explicit at session start but became patterns by session end. Documenting because they're easy to miss in cold-start:

- **Branch from `main` for every commit set** — even single-file bugfixes. The session's first follow-up (the `e7f6af5` → `84cd4a4` autofix bugfix) was committed directly to `main` because of an earlier "push and merge" context; that was a session-guidance break. Fast-forward merge after pushing the branch is the established pattern.
- **Commit message structure**: subject line names the gap (e.g. `Stop baton_precedence_verbatim_anchor false-positives (G19)`); body has WHAT/WHY/HOW + an explicit `pytest tests/ ... unittest discover ...` line confirming both runners. End with `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- **Identity-based regression tests for "don't bypass this guard" invariants.** Both `assertIs(get_validator(), _VALIDATOR)` (G16 L3) and `test_old_constant_is_gone` (G17) use Python object identity / non-existence assertions rather than behavior equivalence. The pattern: when the failure mode is "two code paths drift apart" or "someone re-introduces an unguarded version", identity is the contract.
- **Quarantine entries explain how to un-quarantine.** Both `KNOWN_BROKEN_EVIDENCE_DIRS` entries (`2026-05-18-5ff7a91f`, `2026-05-27-0669899d`) include comments naming the repair recipe. Future quarantine additions should follow.
- **The G## numbering is non-dense and append-only.** Gap numbers don't have to be contiguous (G17 was used after G18 was already published). Pick the next free integer; don't renumber existing gaps.
- **`docs/ecp/` is gitignored.** Anything an audit produces is per-engagement working-tree only. Evidence from a specific engagement that needs to inform repo-level work has to be summarized inline in the relevant doc (this handoff doc is the example).
- **`product.md` § references are load-bearing.** Code comments and commit messages cite `product.md` § X by section number. This keeps the conformance roadmap and the spec tightly coupled. If you ever need to change the spec, log it in `product.md` §10 Spec Change Log — frozen items (§5) only unfreeze via that log entry.

## 11. Suggested skills for the next session

| Skill | When |
|---|---|
| `verify` | After Dan fires the next `/ecp:audit`, before claiming "the new canaries work" — actually inspect the engagement dir for the new outputs (`canonical-frefs-dropped.json`, `[G16]` stderr, autofix repairs log). |
| `verification-before-completion` | Before pushing any post-handoff commit, run `pytest tests/` + `python -m unittest discover -s tests` and confirm both green. |
| `using-superpowers` | At session start (it's always the first thing). |
| `code-review` (`/code-review`) | If a follow-up commit touches more than ~200 lines or modifies the canary suite. The session 5 commits were already moderately reviewed; future ones should keep the bar. |
| `brainstorming` (`superpowers:brainstorming`) | If a new gap surfaces from the next live run and the fix shape isn't obvious — the n=3 → n=5 progression in this session showed how easy it is to misdiagnose with too little evidence. |

NOT suggested:
- `tdd` (red-green-refactor) — overkill for the kinds of small surgical fixes left in the backlog. The session 5 pattern (write the fix + write the regression test in the same commit) is sufficient.
- `frontend-design` and design skills — out of scope for this audit-pipeline work.

## 12. The single highest-leverage thing the next agent can do

**Read this handoff doc, then read [docs/conformance-gaps.md](conformance-gaps.md), then wait for Dan to fire `/ecp:audit`.** Do not start new gap work speculatively — the n=5 progression in this session showed that every confident "I know what's wrong" hypothesis (the ethics steer, the schema drift, etc.) got corrected by the next data point. **Evidence first, then fixes.**

If Dan asks for proactive work before the live run, the best candidate is item #3 (teammate dispatch reliability) — but with the explicit caveat that it can't be fixed in this repo. The right action there is investigation + a written diagnosis, not a code change.

---

_End of handoff. If you're reading this and the live run has already happened, start by diffing the new engagement dir against the n=5 patterns above to see whether the canaries behaved as predicted._
