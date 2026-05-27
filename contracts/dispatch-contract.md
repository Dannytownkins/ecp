# Auditor dispatch contract

Canonical reference for spawning teammates and subagents across all ECP skill coordinators. Contains per-role model assignments, the explicit-model rule, the `--deep` escape hatch behavior, the **v2 dispatch shape policy** (Phase H, 2026-04-28: subagent vs teammate per role), the cluster-auditor (v1 / v2-cluster-specialist) prompt template, and the subagent dispatch contract for the v2-flipped roles.

**Why this file exists:** Prior to Round 12, the dispatch template + model selection rules lived inside `skills/audit/SKILL.md` and `/ecp:build`, `/ecp:compare`, and `/ecp:quick-scan` all deferred to "See `/ecp:audit` `<auditor_dispatch_template>`" for their own spawning logic. That meant those 3 sibling skills had to load the full audit skill (~1500 lines) just to read 100 lines of dispatch rules, AND any change to the rules had to propagate by hand. Round 5 added `--deep` to audit + build but missed compare + quick-scan until Round 9 caught the drift via the addendum review. This file resolves the coupling — dispatch is a first-class canonical reference, no skill owns it.

**Read this file when:** you are the coordinator (lead) of any `/ecp:*` skill that spawns teammates or subagents. That's audit, build, compare, and quick-scan. The audit lead reads this when spawning acquirer (subagent in v2), cluster specialists (teammate), ethics (subagent), synthesizer (subagent), planner/reviewer/builder (subagents in v2). Compare and quick-scan use the same shape per their skill-specific notes below.

**Do NOT read this file if you are a teammate or subagent.** They don't spawn sub-roles — they execute a single task. Workflow / specialist-prompt files contain their own instructions, not this dispatch contract.

---

## The explicit-model rule (MANDATORY)

You MUST pass the `model` parameter explicitly on every single `Agent` tool call. Do NOT rely on parent inheritance.

**Why explicit over inherited:**
- Parent inheritance is silent — if the parent is opus and the spawn doesn't specify, the teammate silently runs on opus even when the spec says sonnet.
- Explicit is auditable — `grep -n 'model: ' skills/ workflows/` gives you the complete dispatch ledger. Inherited is invisible.
- Explicit defends against Round 9's class of bug — where skills shipped with opus hardcoded as the default and nobody noticed until a review pass grepped for it.

**This rule has no exceptions.** Every Agent tool call in every skill passes `model: "sonnet"` or `model: "opus"` inline. If you find yourself reasoning "the parent is already X, it'll inherit," stop — pass it explicitly.

---

## Per-role model + dispatch-shape assignments (canonical, Phase H 2026-04-28)

| Role | Default model | With `--deep` | v2 Dispatch shape | Rationale |
|------|--------------|---------------|-------------------|-----------|
| Acquirer | `sonnet` | `sonnet` (unchanged) | **subagent** (Task tool, no team_name) | Mechanical task — navigate, screenshot, extract DOM, write baton. No synthesis needed. No peer coordination. Subagent eliminates an idle-notification stream the lead never reads. |
| Cluster specialist (a.k.a. cluster auditor) | `sonnet` | `opus` | **teammate** (Agent tool with `team_name`) | Mechanical coverage work — read reference files, apply principles to page, emit JSON-only emission. Stays teammate ONLY because cluster specialists share the engagement output workspace and the lead merges by deterministic file-naming convention. v2 specialists do NOT peer-coordinate (no SendMessage, no huddles) — see `contracts/specialist-prompt-v2.md` "## No coordination" section. |
| Ethics subagent | `sonnet` | `opus` | **subagent** (Task tool, no team_name) | Layer 1.5 in v2 — runs after specialists, before synthesizer. Single-pass page-scope emission. No peer coordination, no shared workspace need beyond writing one JSON file. See `contracts/ethics-subagent-v2.md`. |
| Lead (coordinator) | `opus` | `opus` (unchanged) | n/a — IS the lead | Reconciliation, dedup, Priority Path synthesis, ethics gate processing. The synthesis brain stays on opus. |
| Synthesizer | `opus` | `opus` (unchanged) | **subagent** (Task tool, no team_name) | Layer 3 prose writer. Runs once per engagement, single dispatch with the full canonical-f_refs manifest + cluster emissions trimmed. No peer coordination. See `contracts/synthesizer-v2.md`. |

**The `--deep` escape hatch:** If `--deep` is set in the skill invocation, pass `model: "opus"` instead of `model: "sonnet"` for both cluster auditors AND builder. Everything else stays on its default (acquirer stays sonnet, lead/planner/reviewer stay opus). The flag is a single decision point at the top of the skill — the lead reads `--deep` from the arguments and applies it uniformly. See `${CLAUDE_PLUGIN_ROOT}/contracts/flags.md` for the full `--deep` flag documentation.

---

## Why sonnet is the safe default for cluster auditors and builders

Earlier in this release cycle (2026-04-07 awdmods test), sonnet drifted on FINDING block format — 5 of 10 auditors wrote `### F-SEO-XX` headings instead of code-fenced blocks. That drift is now caught by **four reinforcing guardrails** that did not exist at the time of that test:

1. **Lead-as-validator format check** in `<finding_reconciliation>` Step 0 — reads each cluster file as it arrives, bounces non-compliant files back via SendMessage with corrective instructions. See `${CLAUDE_PLUGIN_ROOT}/contracts/audit-reconciliation.md`.
2. **Lead-as-validator voice check** in `<finding_reconciliation>` Step 0b (added in Round 14) — catches client-tone drift (jargon, compliance-speak, citation-only Why-this-matters) before reconciliation. Also in contracts/audit-reconciliation.md.
3. **`<audit_trace_assertion_header>` canary** — surfaces silent format failures in the numerical counters at audit completion. See `${CLAUDE_PLUGIN_ROOT}/contracts/trace-assertion-canary.md`.
4. **Explicit format examples in `workflows/audit.md` Step 4a + worked voice examples in Step 4b/4c** — sonnet follows concrete examples better than prose descriptions.

With those guardrails in place, sonnet handles format fine. If you ever see a future test where sonnet auditors silently drift past all four guardrails, flip the default back to opus and file a spec gap.

---

## When to pass `--deep` / opus

Pass `--deep` (and therefore use opus for cluster auditors + builder) when:

- **The page is complex** — configurator, multi-step checkout, heavily-designed landing page, React SPA with late hydration, a site you've already audited and sonnet missed subtle findings on.
- **The output will go directly to a client** and quality signal matters more than cost.
- **You're iterating on the spec** and want the strongest baseline for A/B comparison between runs.

Otherwise, omit `--deep` and let the default sonnet multipliers apply. A dual-device 5-cluster audit spawns 10 auditor teammates — sonnet cuts that cost by ~60% compared to opus, without meaningful quality regression on typical pages.

See `${CLAUDE_PLUGIN_ROOT}/contracts/trace-assertion-canary.md` "Cost trace heuristic" for the exact per-role token multipliers that quantify the savings.

---

## v2 Dispatch shape policy (Phase H — 2026-04-28)

v2 flips the v1 default. **Most roles dispatch as one-shot subagents (Task tool, no team_name); only cluster specialists and multi-planner peers remain teammates** (Agent tool with team_name).

### What changes for the lead

| Concern | v1 (teammate everywhere) | v2 (subagent default + teammate exceptions) |
|---|---|---|
| `idle_notification` stream | One per teammate per layer (~70 across acquire → specialists → ethics → synthesize → render) | One per remaining teammate (cluster specialists only); **~5-10 total** |
| Lead context tokens spent on idle pings | Significant — each idle ping is a context entry the lead reads through | Order-of-magnitude smaller |
| Peer coordination via SendMessage | Used in v1 cluster huddles + handoff broadcasts (now unused) | Not used — no audit role peer-coordinates |
| TaskCreate/TaskUpdate ledger | Every teammate claims + completes a task | Cluster specialists + multi-planners only |
| Failure recovery | Lead re-spawns failed teammate via `SendMessage` retry, OR creates a new teammate name | Lead re-dispatches subagent via fresh Task call (no shared task state to clean up) |
| Output workspace | Cluster specialists share `docs/ecp/{engagement_id}/` and rely on deterministic `cluster-{cluster}-{device}.json` naming | Same — cluster specialists keep teammate status precisely BECAUSE of shared workspace |

### Why cluster specialists keep teammate status

Cluster specialists share an engagement directory (`docs/ecp/{engagement_id}/`) and the lead merges their outputs by deterministic file name (`cluster-{cluster}-{device}.json`). The teammate dispatch shape gives:

1. **Atomicity-friendly fanout** (in **waves of ≤5 concurrent spawns**, added 2026-05-27): the lead collects via filesystem glob. A subagent fanout would also work but the existing teammate template handles it cleanly today. **Concurrency cap:** spawn no more than 5 specialists concurrently per wave. The 2026-05-27 batch repeatedly hit transient server-side rate limits ("not your usage limit") at 8+ concurrent spawns — Amazon engagement `0669899d` saw 7 of 8 spawns fail at 0 tokens; slingmods `4a0721e9` lost the entire first 20-way fanout and recovered via waves of ~5. A comprehensive 10-cluster × 2-device run therefore needs ~4 waves of 5 (acquirers count toward the cap; ethics+synthesizer are sequential pinch-points and don't). The 5-cap is operational, not architectural — if a future runtime removes the rate limit, raise it.
2. **Restart-friendly file-presence model.** If the lead resumes mid-run, it reads which `cluster-*-{device}.json` files are already on disk and re-dispatches only the missing ones. The teammate task list is a parallel record but file presence is the truth.
3. **No coordination ceremony.** v2 specialists do NOT SendMessage anyone, do NOT broadcast intent, do NOT propagate SYNTHESIS_HINT. See `contracts/specialist-prompt-v2.md` "## No coordination" section. The teammate dispatch shape is a transport choice, not a coordination requirement.

### How to dispatch each role in v2

| Role | Template / prompt source | Tool call |
|---|---|---|
| Acquirer | `workflows/acquire.md` | `Task(subagent_type="general-purpose", model="sonnet", prompt=<acquire workflow>)` |
| Cluster specialist | `contracts/specialist-prompt-v2.md` (with per-cluster params from `contracts/specialists/{cluster}.md`) | `Agent(subagent_type="general-purpose", team_name="audit-{engagement_id}", name="specialist-{cluster}-{device}", model="sonnet", prompt=<rendered template>)` |
| Ethics subagent | `contracts/ethics-subagent-v2.md` | `Task(subagent_type="general-purpose", model="sonnet", prompt=<rendered ethics template>)` |
| Synthesizer | `contracts/synthesizer-v2.md` | `Task(subagent_type="general-purpose", model="opus", prompt=<rendered synthesizer template with canonical_f_refs_manifest>)` |

### What stays the same

- **The explicit-model rule** (every dispatch passes `model: ...` inline; never inherit from parent).
- **Sonnet vs Opus assignment per role.** The flip is about *transport* (subagent vs teammate), not about model choice.
- **The `--deep` escape hatch** — affects model choice for cluster specialists + builder only, dispatch shape is unchanged.
- **The forensic-trace assertion canary.** Counter names evolve to reflect the new shape; see "Assertion counter update on spawn" below for the v2 counter set.

---

## Auditor prompt template (for cluster specialists — teammate dispatch in v1 + v2)

> **v2 note:** v2 cluster specialists use `contracts/specialist-prompt-v2.md` as the canonical prompt template — that template emits JSON-only against `schema/cluster-emission-v1.json` and explicitly documents "## No coordination" (no SendMessage, no huddles, no SYNTHESIS_HINT propagation; see lines 178-182 of that file). The template below is the v1 markdown-emission template, retained for v1 audit compatibility. **Do NOT propagate this template's huddle/handoff broadcast machinery into the v2 specialist template** — the §3.8 / §17.7.6 / §19.2 coordination ceremony is closed in v2.

When the lead spawns a cluster auditor teammate, the Agent tool call uses these exact parameters:

```
Agent tool call:
- subagent_type: "general-purpose"
- team_name: "audit-{engagement-id}"
- name: "auditor-{cluster}-{device}"   (e.g., "auditor-pricing-mobile")
- model: "sonnet"   ← DEFAULT (pass "opus" ONLY if --deep flag is set)
- prompt: [the prompt template below]
```

**Prompt template:**

```
You are joining the **audit-{engagement-id}** team as **auditor-{cluster}-{device}**. Your job: audit a {device} viewport ({width}×{height}) for the **{cluster}** cluster of e-commerce psychology findings.

## Team context
- Team name: `audit-{engagement-id}`
- Your name: `auditor-{cluster}-{device}`
- Other teammates: see `~/.claude/teams/audit-{engagement-id}/config.json` for the full member list
- Lead: `team-lead`

## Your task
Claim task `audit-{cluster}-{device}` from the team task list (TaskUpdate with owner=your name, status=in_progress).

## Your Reference Files (READ ALL BEFORE AUDITING)
Read these reference files at ${CLAUDE_PLUGIN_ROOT}/references/:
{{reference_file_list}}

## Page Data
- **Screenshots** (PRIMARY visual evidence): {{screenshot_paths_with_descriptions}}
- **Cluster context file**: {{cluster_context_path}} (JSON file with per-cluster DOM slices, page head, filtered elements, and styles — produced by the lead's DOM preprocessor. Read this file for your DOM content. Do NOT read the full `dom.html` / `dom-mobile.html` — it contains the entire page and is not filtered to your cluster.)
- **Device**: {{device}} at {{width}}×{{height}}, {{dpr}}x DPR
- **Page type**: {{page_type}} ({{platform}})

**Pixel units in the cluster context file are CSS pixels.** The DOM preprocessor has already normalized `elements[].x`, `elements[].y`, `elements[].width`, `elements[].height` by the viewport DPR. A 390-wide iPhone viewport reports element y-coordinates up to ~844 for above-fold elements, not 2532. Do NOT quote screenshot pixel numbers in your TITLE or OBSERVATION — write in CSS px or as viewport ratios. See `workflows/audit.md` §FORMAT CONTRACT "Pixel units" for the rule and the linter that enforces it.

## Ethics Gate
{{full_ethics_gate_content}}

## Audit Instructions
[Read and include content from ${CLAUDE_PLUGIN_ROOT}/workflows/audit.md]

## Evidence requirement (MANDATORY — finding-level gate)
Every finding you emit MUST cite at least one concrete evidence anchor from THIS page. Acceptable anchors:

1. A **DOM selector** matching a specific element present in `{{cluster_context_path}}` (e.g., `button.add-to-cart-hero`, `div.product-reviews[data-count="0"]`).
2. A **screenshot region** with an approximate coordinate reference (e.g., "top-right quadrant of mobile hero, ~340×220 at 0,120").
3. A **verbatim quoted copy string** of ≥3 consecutive words that actually appears in the acquired DOM text (e.g., "Add to cart — in stock").

If you cannot identify at least one anchor for a finding, **do not emit it**. Generic CRO advice without a page anchor will be rejected by the reconciliation Step 0c evidence-anchor gate (see `${CLAUDE_PLUGIN_ROOT}/contracts/audit-reconciliation.md`) and bounced back to you for rewrite. Evidence-tier classification per `${CLAUDE_PLUGIN_ROOT}/references/evidence-tiers.md` requires both a credible source AND a page anchor — a Gold-publisher citation without a page anchor is downgraded to Bronze.

## Forbidden framings (DO NOT use these phrases)
These phrasings mark a finding as page-agnostic (could be pasted into any audit of any store). Do not emit them verbatim or as close paraphrase:

- "consider adding X"
- "best practice suggests"
- "typical stores benefit from"
- "industry standard is"
- "users often expect"
- "research shows that"

If your evidence points to a pattern the page lacks, name what is actually on the page and describe the specific absence, not the generic advice.

### Worked example — acceptable (page-anchored)
```
FINDING: FAIL
SECTION: hero-layout
ELEMENT: button.add-to-cart-hero
PRIORITY: HIGH
OBSERVATION: The "Add to cart" button below the hero uses #FF6B35 text on the #F7F3EC hero panel. The contrast ratio is 2.8:1 — on the desktop viewport at normal brightness the button reads as a muted orange blur against the ecru panel, not as the page's primary action.
RECOMMENDATION: Darken the button to #D9480F (4.6:1 against the ecru panel). That clears WCAG AA on a 14px button and makes the button dominate the hero area visually.
↳ color-psychology.md — Finding 3 [Silver]
```
Why acceptable: specific DOM element, measured contrast ratio from the acquired styles, quoted hex values, named observable effect. Another auditor could verify against the same page.

### Worked example — unacceptable (generic, will be rejected)
```
FINDING: FAIL
SECTION: hero-layout
ELEMENT: (unspecified)
PRIORITY: MEDIUM
OBSERVATION: The hero section could benefit from a stronger call-to-action. Best practice suggests using high-contrast colors for primary buttons.
RECOMMENDATION: Consider adding a more prominent CTA button. Users often expect the primary action to stand out visually.
↳ cta-design-and-placement.md
```
Why unacceptable: no DOM element, no measured evidence, no quoted copy. Contains three forbidden framings ("could benefit from", "best practice suggests", "consider adding", "users often expect"). The observation and recommendation would apply unchanged to any e-commerce store. Step 0c rejects; you will be bounced back to rewrite with a concrete anchor.

## Output
Write your findings to: `docs/ecp/{engagement-id}/cluster-{cluster}-{device}.md`

Use the same finding block format as audit.md (triple-backtick code fences around each FINDING block).

## Team coordination (MANDATORY — read `workflows/audit.md` §Step 1b and §Handoff broadcast)

Cluster auditors ran silently through the 2026-04-21 engagement — they all started in parallel, produced their findings in isolation, and the lead reconciled text blobs without any runtime peer knowledge. The result: duplicated findings across clusters, missed cross-cluster overlaps, and a Priority Path synthesizer operating on 56 findings it had to group by its own heuristics because the auditors never coordinated.

Two broadcasts are now MANDATORY:

**1. Intent huddle at Step 1b (BEFORE auditing):**

```
SendMessage to "*":
"[auditor-{cluster}-{device}] Starting. Primary surfaces I'll examine: {top 3 SECTION slugs}. Flag if you're touching any of these."
```

Don't wait for replies. If another auditor raises a hand about overlap, align a SYNTHESIS_HINT slug and move on.

**2. Handoff broadcast after writing your cluster file:**

```
SendMessage to "*":
"[auditor-{cluster}-{device}] Complete — {N} findings. Top 3: {F-01 title} ({SEVERITY}) | {F-02 title} ({SEVERITY}) | {F-03 title} ({SEVERITY}). File: cluster-{cluster}-{device}.md."
```

Plus a DM to `team-lead`:

```
SendMessage to "team-lead":
"Done. Findings at docs/ecp/{engagement-id}/cluster-{cluster}-{device}.md"
```

**Per-finding overlap flag (optional, use when cross-cluster overlap is detected mid-audit):**

```
SendMessage to "auditor-{other-cluster}-{device}":
"I (auditor-{cluster}-{device}) flagged {element} at {scroll position}. If you're covering this area, tag SYNTHESIS_HINT: {shared-slug} so the reconciler groups us."
```

## Completion
1. Mark your task complete: TaskUpdate with status=completed
2. Fire the handoff broadcast to the team (above)
3. DM `team-lead` with the short "Done. Findings at..." line
4. Go idle. The lead will collect your findings during reconciliation.

If you fail or partially complete (STATUS: PARTIAL), mark the task complete with a status note explaining what was missing. The lead will decide whether to retry.
```

**Template notes:**
- `{{cluster_context_path}}`: The per-cluster context file produced by the lead's DOM preprocessor (`<dom_preprocessor>` in `skills/audit/SKILL.md`). Format: `cluster-context-{cluster}-{device}.json`. Contains: per-section DOM slices, page head (meta/schema/canonical), filtered elements, and extracted styles. For file-path mode (no DOM preprocessor), pass the source file path directly instead.
- `{{full_ethics_gate_content}}`: The COMPLETE text of `${CLAUDE_PLUGIN_ROOT}/references/ethics-gate.md` — do not summarize, paraphrase, or excerpt.
- `{{reference_file_list}}`: The list of cluster-specific reference files from `${CLAUDE_PLUGIN_ROOT}/contracts/cluster-routing.md` "The 10 clusters" table, matching the auditor's assigned cluster.

---

## Assertion counter update on spawn

**After every successful dispatch** (whether `Agent` for teammates or `Task` for subagents), the lead MUST increment the corresponding counter in `audit-trace.log`. The counter is the structural truth of the run; if you spawn N roles, the counter says N. If you don't spawn any, the counter says 0 — and the assertion self-check at audit completion will catch you.

### v2 counter set (Phase H — 2026-04-28)

The v2 dispatch flip introduces `subagent_spawned_*` counters alongside the existing `team_spawned_*` counters. The audit lead writes both:

| Role | Dispatch shape | Counter name to increment |
|---|---|---|
| Acquirer | subagent | `subagent_spawned_acquirers` |
| Cluster specialist | teammate | `team_spawned_specialists` (renamed from `team_spawned_auditors` in v2; v1 backwards-compat alias accepted) |
| Ethics subagent | subagent | `subagent_spawned_ethics` |
| Synthesizer | subagent | `subagent_spawned_synthesizer` |

**Backwards compatibility:** v1 audit runs continue to increment `team_spawned_acquirers` and `team_spawned_auditors`. The audit-completion self-check accepts EITHER counter as valid evidence the role ran. v2 runs SHOULD use the new counter names; the assertion check treats `subagent_spawned_acquirers >= 1` and `team_spawned_acquirers >= 1` as equivalent for the purpose of "acquirer ran at least once."

See `${CLAUDE_PLUGIN_ROOT}/contracts/trace-assertion-canary.md` for the full counter contract and self-check rules, including the v2 header format.

---

## Subagent dispatch contract (v2 default)

For roles dispatched as one-shot subagents (acquirer, ethics, synthesizer, planner-single, reviewer, builder), the lead uses the `Task` tool — NOT the `Agent` tool. This is the structural difference between subagent and teammate dispatch.

### Tool-call shape

```
Task(
  subagent_type="general-purpose",
  description="<3-5 word imperative summary of the role's work>",
  model="<sonnet | opus per the per-role table above>",
  prompt=<rendered role-specific prompt template>
)
```

There is no `team_name` parameter (so the subagent does not join the team), no `name` parameter (so there's no per-role handle for SendMessage), and no shared task-list claim/complete cycle.

### Why subagents instead of teammates for these roles

1. **They don't peer-coordinate.** The roles flipped to subagent in v2 (acquirer, ethics, synthesizer, planner, reviewer, builder) never SendMessage another role at the same layer. v1 created teammates uniformly; v2 reserves teammate shape for the roles that genuinely need shared workspace (cluster specialists) or peer messaging (multi-planner peers).
2. **Idle notifications collapse.** A teammate that's idle pings the lead's mailbox until it gets a task or is dismissed. A subagent runs once, returns, and exits — no idle stream.
3. **Lead context shrinks.** Each idle notification is a context entry the lead reads through. ~70 idle pings (v1) → ~5-10 (v2).
4. **No team-state cleanup.** A subagent that fails leaves no zombie task on the team task list; the lead just dispatches a fresh subagent.

### Handling questions / clarifications from a subagent

A subagent can't SendMessage during execution. v1's reviewer/builder Q&A loops (relay-loop-protocol.md) used SendMessage during the teammate's run; v2 reviewer/builder pose questions in their final emission (a structured `questions[]` field). The lead surfaces them inline at `<checkpoint_review>` / `<checkpoint_build>` and re-dispatches a fresh subagent with the answers if the operator wants iteration. The relay-loop-protocol.md is preserved for v1 backwards compat but the v2 path doesn't need it.

### Failure recovery

If the subagent's prompt produces malformed output, validation failure, or no useful response:
1. **Retry once** — re-dispatch a fresh `Task` call with the same prompt plus an embedded validation error (e.g., "Your prior emission failed schema validation: <error>. Re-emit a single valid JSON object."). Increment a `subagent_retried_<role>` counter.
2. **On second failure** — mark the role's output `status: "partial"` (or skip the layer with a SKIP marker) and continue. Document in `audit-trace.log` and `lead-reflection.md`.

### Cancel.flag check

Before EACH subagent dispatch (and at every layer boundary in the audit pipeline), the lead checks `<engagement-dir>/cancel.flag`. If the file exists, the lead writes `engagement_status: cancelled_by_operator` to `audit-trace.log` and exits cleanly with partial artifacts preserved. See `contracts/lead-discipline.md` "Cancellation sentinel (cancel.flag)" section.

---

---

## Cross-references

- **`skills/audit/SKILL.md`** — the audit router defers to this file for dispatch shape.
- **`${CLAUDE_PLUGIN_ROOT}/contracts/flags.md`** — canonical `--deep` flag documentation.
- **`${CLAUDE_PLUGIN_ROOT}/contracts/trace-assertion-canary.md`** — spawn counter contract + cost trace heuristic.
- **`${CLAUDE_PLUGIN_ROOT}/contracts/audit-reconciliation.md`** — the format + voice validation guardrails that make sonnet default safe.
- **`${CLAUDE_PLUGIN_ROOT}/contracts/cluster-routing.md`** — source of truth for `{{reference_file_list}}` per cluster.
- **`${CLAUDE_PLUGIN_ROOT}/contracts/device-semantics.md`** — source of truth for `{{dom_path}}` + dual-device session isolation.
- **`${CLAUDE_PLUGIN_ROOT}/references/ethics-gate.md`** — canonical ethics content interpolated as `{{full_ethics_gate_content}}`.

When editing this file, grep all 4 skill files + `workflows/acquire.md` + `workflows/audit.md` for any `model: "sonnet"` or `model: "opus"` literals and verify each still matches the per-role table above. Drift in model assignments is the highest-risk class of bug in the whole plugin because it silently changes cost and quality.
