# Archived Cursor agents (frozen — NOT canonical)

These five `ecp-*.md` agent definitions are the **Cursor** runtime's subagent
prompts. They are **archived, not shipped**, per `product.md` §8 ("Codex and Cursor
are archived, not shipped … re-portable from the archive if ever wanted, but not
part of the canonical product") and §5 (Frozen Scope & Reserved Seams).

## Why they live here and not in `agents/`

They used to sit in the repo-root `agents/` directory. Claude Code auto-discovers
`agents/*.md` as selectable subagent types — so even though no `skills/`,
`contracts/`, or `workflows/` file wires these in, the audit lead could *see* them
in the Agent tool's type list and infer a delegation path from their **presence**
alone. In engagement `docs/ecp/2026-05-28-e4050c0e` the lead surfaced
*"Delegate to ecp-orchestrator (Recommended)"* as a dispatch option that the
canonical SKILL never authorizes. The role ("orchestrator") was always just the
audit lead under a Cursor-flavored name; reading the file's name literally created
a phantom delegation target.

This is the same "freeze-as-invariant fails in practice" pattern as G16, G17, and
G22+G24: a concept frozen in docs but left on a discoverable surface stays live.
To freeze something operationally, **move the surface out of discovery scope** —
don't just mark it out of scope in prose. Relocating here removes them from Claude
Code's `agents/` auto-discovery while keeping them re-portable, exactly as §8 says.

## The canonical Claude Code dispatch path (what these are NOT)

Under `/ecp:audit`, the audit lead dispatches work via the **Agent/Task tools to the
inline subagent contracts** — `contracts/specialist-prompt-v2.md`,
`contracts/ethics-subagent-v2.md`, `contracts/synthesizer-v2.md`, and the canonical
acquirer `scripts/acquire_url.py`. The lead NEVER delegates to an `archive/cursor-agents/*.md`
file. See `skills/audit/SKILL.md` § "Dispatch Shape".

## Un-freezing (if Cursor is ever revived as a canonical runtime)

1. Add a dated Spec Change Log entry to `product.md` §10 that unfreezes the Cursor
   runtime (§5 frozen scope unfreezes ONLY via such an entry — never implicitly).
2. Re-prove conformance to `product.md` and the frozen contracts (§7).
3. Only then relocate these back into a discoverable location.
