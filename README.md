# ECP — E-Commerce Conversion-Psychology Audit

A Claude Code plugin that audits a single ecommerce page (from a URL) against an
evidence-tiered research library and produces **cited, element-anchored findings**, a
prioritized **Priority Path**, and an **annotated visual report** with an editable
hotspot tool. An **ethics gate** runs on every audit.

> **`product.md` is the canonical spec.** It defines exactly what ECP is and isn't,
> the trust invariants, frozen scope, and the governance rule. If anything in this
> README, the code, or the CHANGELOG disagrees with `product.md`, `product.md` wins.

## What it is (and isn't)

- **Is:** a single-page conversion-psychology **auditor** — findings + Priority Path +
  visual report, then it stops.
- **Isn't:** a measurement/A-B tool, an exhaustive technical auditor (Lighthouse/axe),
  legal/compliance advice, or a site crawler/auto-fixer. See `product.md` §3.

Build, compare, quick-scan, and resume modes — and the Codex/Cursor runtimes — were
archived with the previous repo and are **out of scope** in this build (`product.md` §5).

## Setup (one time)

```powershell
python -m venv .venv ; .\.venv\Scripts\Activate.ps1 ; pip install -r requirements.txt
npm install        # playwright (acquisition) + the hotspot editor
```

## Run

Load the plugin live from this repo (no cache, edits take effect immediately):

```powershell
& "<path-to>\claude.exe" --plugin-dir "<path-to>\ecp"
```

Then, inside that session:

```
/ecp:audit https://your-product-page --visual
```

Useful flags: `--device mobile|laptop|desktop` (or a comma pair), `--focus <domains>`,
`--deep`, `--min-priority`, `--platform`, `--auto`. The full flag reference is
`contracts/flags.md`.

Outputs land in `docs/ecp/<engagement-id>/` (`audit.md`, `visual-report.html`, …).
A generated report is a **DRAFT** until you complete the manual verification pass
(re-check the live site, verify legal/ethics citation links, finalize hotspots) —
see `product.md` §6.

## Layout

| Path | What |
|---|---|
| `product.md` | Canonical spec (read this first) |
| `skills/audit/` | The `/ecp:audit` router |
| `contracts/` | Runtime contracts (dispatch, routing, schema, ethics, …) |
| `workflows/` | `acquire.md`, `audit.md` |
| `references/` | The evidence-tiered research library (the moat) |
| `scripts/assembly/`, `scripts/report/` | Audit assembly + report rendering |
| `tools/editor/` | The annotated-report hotspot editor |
| `schema/`, `citations/`, `templates/` | Validation schemas, source registry, report assets |

## Known limitations

- **Acquisition (Windows):** `scripts/acquire_url.py` can fail to acquire
  large pages because `agent-browser eval` mangles long inline JS args on Windows.
  This is the current top fix target — see the engagement notes / `product.md` change log.
- Hotspot placement is precision-first: low-confidence hotspots are left **blank** for
  manual placement rather than auto-placed wrong (`product.md` §4.2).

## History

This repo is a clean prune-and-re-root of `ecommerce-conversion-psychology` (2026-05-26).
The full pre-1.0 history, the archived modes/runtimes, and prior CHANGELOG eras live in
that archived repo.
