# Canonical f_refs manifest

USE ONLY THESE f_refs in priority_path[].f_refs, scope_page_synchronized_refs,
quick_wins_manifest, severity_manifest, humanized_findings[].f_ref, and as the
heading suffix on each finding subsection in audit-{device}.md.

Format: `{cluster} F-{NN}` (zero-padded). The NN integer is
**content-hash-derived** (sha256(surface|baton_index|verdict)[:6] mod 99 + 1)
per `scripts/assembly/pipeline.py:assign_display_indices`. The renderer
re-derives the same hash at parse time and rejects mismatched refs as
out-of-allowlist — paste these integers verbatim, do NOT renumber.

| f_ref | severity | devices_present | title |
|---|---|---|---|
| `category-navigation F-19` | HIGH | desktop | Vehicle Fitment Selector Buried as Tertiary CTA |
| `category-navigation F-05` | HIGH | mobile | Search Bar Has No Fitment Binding |
| `category-navigation F-51` | HIGH | desktop | Featured Grid Cards Missing Review Counts |
| `category-navigation F-84` | HIGH | mobile | Subcategory Carousel Has No Scroll Affordance |
| `category-navigation F-45` | HIGH | mobile | Featured Collection Renders One Card Per Row |
| `category-navigation F-59` | HIGH | mobile | No Persistent Vehicle Selector After Find Parts |
| `category-navigation F-28` | MEDIUM | desktop | Made to Order Badge Repeated on Every Card |
| `category-navigation F-96` | MEDIUM | desktop | Featured Grid Pushed to 5 Columns at 1920px |
| `category-navigation F-04` | MEDIUM | mobile | Lead Featured Card Missing Star Rating |
| `category-navigation F-03` | MEDIUM | desktop | Search Placeholder Misses Fitment Query Pattern |
| `category-navigation F-87` | MEDIUM | mobile | No View-All Exit on Featured Collection |
| `category-navigation F-06` | MEDIUM | desktop | Featured Collection Lacks View All Affordance |
| `category-navigation F-12` | LOW | desktop | Subcategory Tile Row Routes Visitors by Build Goal |
| `category-navigation F-98` | LOW | mobile | Search Bar Visible at Top, Not Hidden Behind Icon |
| `visual-cta F-12` | HIGH | desktop | Hero Has No Headline or Value Proposition |
| `visual-cta F-24` | HIGH | mobile | Hero Lacks Headline And Value Proposition |
| `visual-cta F-37` | HIGH | desktop | No Primary CTA Button in Hero |
| `visual-cta F-36` | HIGH | mobile | Find Parts Button Has Washed-Out Contrast |
| `visual-cta F-67` | HIGH | mobile | No Sticky CTA After Hero Scrolls Off |
| `visual-cta F-38` | MEDIUM | desktop | No Above-Fold Trust Signal |
| `visual-cta F-13` | MEDIUM | desktop | Five Equal-Weight Category CTAs Compete |
| `visual-cta F-04` | MEDIUM | mobile | Quick-Add Plus Icon Lacks Textual Affordance |
| `visual-cta F-69` | MEDIUM | mobile | Featured Collection Heading Is Generic |
| `visual-cta F-89` | MEDIUM | desktop | Search Input Dominates Above-Fold Real Estate |
| `visual-cta F-77` | MEDIUM | mobile | Newsletter Subscribe Button Is Icon-Only |
| `visual-cta F-52` | MEDIUM | mobile | Category Card Buttons Sit Below Card Fold |
| `visual-cta F-39` | LOW | desktop | Top Promo Bar Buries Free Shipping Threshold |
| `visual-cta F-11` | LOW | mobile | Cart Icon Has No State Indicator |

_Total: 28 canonical f_refs across 2 cluster(s)._