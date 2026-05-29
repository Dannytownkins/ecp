# Durable v1→v2 baton converter — design spec

**Date:** 2026-05-29 · **Status:** Approved · **Author:** Dan + Claude (Opus 4.8)

## Context

The v2 audit pipeline consumes `schema/baton-v1.json`-shaped batons (`e_index`
elements, `rect`, disjoint `sections`, `page_head`, `capture_state`). The legacy
capture engine `scripts/acquire_url.py` emits a *v1-shape* baton (flat
`x/y/width/height` elements, scroll-slice `sections`, `screenshots[]`, no
`e_index`/`page_head`/`capture_state`).

When a v1 baton must be run through the v2 pipeline **without re-acquiring** (a
recovery scenario), it has to be converted. Today that conversion is done by
hand-written, per-engagement scripts (`scripts/one_off/convert_<eng>_batons.py`)
that are copy-adapted each run and carry latent bugs. The only shared converter,
`scripts/adapt_v1_baton_to_v2.py`, is explicitly "throwaway scaffolding" — it
nulls `page_head`, pulls sections from `cluster-context-*` files instead of the
baton, and exists for Phase B smoke testing only. The result: people keep
writing fresh per-engagement copies. Those copies are now gitignored as
per-engagement scratch (see the `.gitignore` "per-engagement baton converters"
block).

## Goal

One durable, tested, parameterized converter that **supersedes** both the
throwaway adapter and the per-engagement copies, producing output **faithful to
what the production acquirer emits**.

## Non-goals (YAGNI)

- **Screenshot renaming.** Precondition: canonical `section-N.jpg` /
  `section-N-mobile.jpg` files already exist on disk. The converter emits
  canonical refs and warns if a referenced file is missing; it does not rename.
- **Baton trimming** (`trim_*`) — a separate concern, out of scope.
- **Auto-wiring into an automated recovery flow.** Manual invocation only.

## Evidence (validated against real data)

Validated field-by-field against the completed `docs/ecp/2026-05-29-3e7bd452`
engagement's `baton.v1raw.json` (input) → `baton.json` (output) pair:

- **Per-section `clusters` are advisory.** `dom_preprocess._route_clusters_for()`
  never returns falsy (it self-falls-back to `["visual-cta","content-seo"]`), so
  the `or sec.get("clusters")` term at `scripts/dom_preprocess.py:418` is an
  unreachable dead branch. Downstream routing is 100% label-driven, with
  `_is_global` (scroll_y=0) fanning the above-fold section into every cluster.
  The prototypes' all-6-clusters stamp was therefore **functionally inert** and
  mildly misleading. → The converter mirrors the acquirer (preserve, else
  enrich); it does **not** replicate the all-6 stamp.
- v1 element rects are already G14-clamped at source
  (`_dpr_scale_element_css_to_phys`); the converter re-clamps defensively for
  older batons.
- v1 `screenshots[].path` (e.g. `"desktop-section-1.jpg"`) is stale relative to
  the on-disk + schema-canonical `section-N.jpg`. The converter computes the
  canonical ref and ignores `path`.
- Confirmed output: `page_height_px:2920`, disjoint bottoms `899<900`,
  `1799<1800`, `page_head` extracted (`canonical`, `meta_description`,
  `viewport_meta`, `og_image:null` tolerated), `dpr_actual` from `dpr_fallback`.

## Design

**Module:** `scripts/baton_v1_to_v2.py` — pure core + thin I/O wrapper + CLI.

### Public API

- `convert_baton(v1: dict, dom_html: str, *, device: str, engagement_id: str) -> dict`
  — **pure**, no I/O. Returns a `schema/baton-v1.json`-valid dict or raises
  `BatonConversionError` (with the first ~8 validation errors).
- `convert_engagement(engagement_dir: Path, *, devices=("desktop","mobile"), out_dir=None) -> dict`
  — per device: read `baton{,-mobile}.json` + `dom{,-mobile}.html`; back up the
  source to `*.v1raw.json` (idempotent: skip if a backup already exists);
  `convert_baton`; **schema-validate, then** `atomic_write_json` in place (or to
  `out_dir`); warn (don't fail) if a referenced `section-N.jpg` is missing.
  Missing baton for a device → skip with a message.
- `main(argv) -> int` — CLI:
  `python scripts/baton_v1_to_v2.py <engagement-dir> [--device both|desktop|mobile] [--out-dir DIR] [--engagement-id ID]`.
  Defaults: both devices, in-place.

### Reuse (faithful core)

- `ecp_section_hints`: `section_label`, `make_section_labels_unique`,
  `enrich_baton_sections` — exactly as `acquire_url.py` (lines 1094–1096) uses
  them. **No invented routing policy.**
- `assembly.atomic_write.atomic_write_json` for writes.
- `schema/baton-v1.json` + `jsonschema.Draft202012Validator` for validation.

### Field mapping

| v2 field | Rule |
|---|---|
| `elements[].e_index` | `e{i}`, sequential DOM order |
| `elements[].rect` | v1 `x/y/width/height`, **re-clamped `max(0.0, …)` (G14)** |
| `elements[].role` | `IMPLICIT_ROLE.get(tag, "group")` |
| `elements[].is_above_fold` | `y < viewport.height` |
| `elements[].is_offscreen` | `not v1.visible` |
| `sections[].clusters` | **preserve v1; `enrich_baton_sections()` only if empty** |
| `sections[]` scroll range | sort by `scrollY`; normalize disjoint (`bottom[i] = min(raw, next_top-1)`; last clamped to `page_height`) |
| `sections[].slug` | slugify(label) |
| `sections[].screenshot_ref` | `section-{screenshot_index}.jpg` / `-mobile.jpg` (schema regex) |
| `page_head.*` | parse `<head>`: `canonical`, `meta_description`, `viewport_meta`, `og_image`, `hreflang` |
| `page_head.title` | **omit when empty** (schema `title` is non-nullable string) |
| `page_head.schema_jsonld` | from v1 `structured_data` |
| `capture_state.hydration` | `pre-hydration` if `pre_hydration_warning` else `post-hydration` |
| `capture_state.page_height_px` | `max(element bottoms, section bottoms, viewport.height)` |
| `viewport.dpr_actual` | `1.0 if dpr_fallback else dpr` |
| `engagement_id` | dir name, validated `^\d{4}-\d{2}-\d{2}-[0-9a-f]{8}$`; `--engagement-id` override |

### Error handling

Schema-validate before any write; on errors, print the first ~8 and
raise/exit 1, writing nothing. Missing `dom.html` → `page_head` fields `null`
(schema-allowed) + warn.

## Supersede

- Delete `scripts/adapt_v1_baton_to_v2.py` (its only consumer is one test).
- Repoint `tests/test_baton_rect_clamp.py::TestAdapterClamps` to assert the
  clamp idiom on `scripts/baton_v1_to_v2.py` (keeps the G14 regression alive).

## Tests (`tests/test_baton_v1_to_v2.py`)

Synthetic v1 dict + a small DOM string → assert: schema-valid; sequential
`e_index`; negative rects clamp to 0; disjoint sections; `screenshot_ref`
regex; `title` omitted when empty; clusters preserved vs enriched; `page_head`
parsed; `engagement_id` regex validation + `--engagement-id` override. Plus a
round-trip smoke test mirroring the `3e7bd452` shape.

## Commit / push cadence (small chunks, each pushed)

0. Hygiene `e08ea70` (already committed) — `--quality` removal + gitignore.
1. This spec doc.
2. Failing tests (`tests/test_baton_v1_to_v2.py`) — TDD red.
3. Pure `convert_baton` core — tests green.
4. `convert_engagement` + `.v1raw.json` backup + `main()` CLI.
5. Supersede: delete `adapt_v1_baton_to_v2.py` + repoint `test_baton_rect_clamp.py`.
6. Final: both runners green; optional validation against the `3e7bd452` fixture.

**Verify both runners (`pytest tests/` + `python -m unittest discover -s tests`)
before every code push.**

## Retires

Once landed, the three gitignored scratch scripts
(`scripts/one_off/convert_{3e7bd452,b0051311}_batons.py`,
`scripts/trim_batons_phase5.py`) are obsolete and may be deleted from disk.
