# Audit — AWDMods Homepage (mobile)

## Executive Summary

The mobile hero presents a value-prop-free vehicle picker overlaid on a stock car photograph, with a half-transparent FIND PARTS button that visually dissolves into the underlying car body. Once a visitor scrolls past the hero, no sticky CTA remains and the captured vehicle does not persist across navigation, so the entire fitment funnel breaks on the first scroll. Below the fold, the Featured Collection renders one card per row and four of five category tiles sit hidden behind an undiscoverable horizontal swipe. Start with the hero (headline, opaque button, sticky CTA, persistent vehicle chip), then convert the Featured Collection to a 2-column grid and add scroll affordances to the category carousel.

## Ethics Gate

One ADJACENT finding: the footer Privacy Policy link points to a `myshopify.com` staging-domain host instead of the canonical storefront. Disclosure exists, but the chain-of-disclosure is fragile and a one-line config fix.

## Top Priorities

### Rebuild the Mobile Hero with Headline, Opaque CTA, and Persistent Vehicle Context

The mobile hero stacks a generic search bar, four empty `Select Make / Model / Year / Trim` dropdowns, and a translucent `FIND PARTS` button over a stock WRX photograph — with no headline, no subhead, and a primary CTA whose white label dissolves into the white car body behind it. Compounding the failure, the captured vehicle does not persist after Find Parts: a visitor who picks 2018 Focus RS and clicks the logo back to home has no visual confirmation the catalog is filtered and must re-select on every return. Add a one-line headline above the picker (`Performance parts for Focus RS, Focus ST, WRX and STI.`) plus a one-line subhead (`Fitment-checked for your exact trim. Free shipping over $75.`); make the FIND PARTS button a 100%-opaque brand-blue fill with a 1-2px darker border and verified 4.5:1 text contrast; and persist the selected vehicle in localStorage with a `Shopping for: 2018 Focus RS [Change] [Clear]` chip rendered in the sticky header on every page.

Refs: visual-cta F-24, visual-cta F-36, category-navigation F-59

### Add a Sticky Find Parts Bar and Bind Search to the Selected Vehicle

Once the hero scrolls off (around y=810) the mobile page has no persistent conversion action — only an unlabelled cart icon in the top header. Meanwhile the search bar accepts free-text queries with a generic `Search` placeholder and pipes none of the captured fitment data into results, so a shopper who types `cold air intake` gets every intake in the catalog including parts that do not fit their car. Render a slim sticky bottom bar (under 56px) that becomes either `FIND PARTS for [Selected Vehicle]` once the picker has been used or `Pick your vehicle` otherwise, and bind the search input to the persisted vehicle so autocomplete and results pre-filter to fit-confirmed parts. Display an active vehicle chip inside the search bar (`Searching: 2018 Focus RS`) and rotate the placeholder through three concrete fitment examples to coach query vocabulary.

Refs: visual-cta F-67, category-navigation F-05

### Convert Featured Collection to a 2-Column Grid with Star Rows on Every Card

The Featured Collection on mobile shows one product card occupying nearly the full viewport width (266px image in a 390px frame) with the second card peeking — a wide-card carousel that consumes ~700 vertical pixels per product and forces four swipes to see the same five products a 2-column grid renders in one screen. The asymmetry compounds: the lead VelourTex card has no star rating row while the next card (Revo Designs Rocker Stripes) shows `5.0 / 5.0 (2)`, training shoppers to discount the rating signal across the whole grid. Switch to a 2-column grid with consistent card heights (1:1 image, 2-line title with ellipsis, price, badge), always reserve the rating row in the template (`Be the first to review` for zero-review products), and add a `View All` link to the right of the `Featured Collection` heading plus a terminal `See all 24 products in this collection →` card.

Refs: category-navigation F-45, category-navigation F-04, category-navigation F-87, visual-cta F-69

### Surface the Five Subcategory Tiles and Label the Quick-Add Action

Only the Performance tile is visible above the fold — the four other subcategories (Handling, Interior, Exterior, Electronics) sit fully offscreen with no dot indicator, no chevron, and no peek of the next card to signal swipeability. On the product cards below, the only conversion action is an orange square with a white `+` glyph in the corner, with no text label telling a thumb-scrolling visitor whether tapping it adds to cart, opens a quick-view, or saves to wishlist. Drop the carousel and render the five tiles as a 2-column grid (Performance/Handling, Interior/Exterior, Electronics spanning row three) so all five are visible without interaction, and replace the `+` icon with a labelled, full-width 48px-tall `Choose Options` or `Add to Cart` button under each card's price.

Refs: category-navigation F-84, visual-cta F-52, visual-cta F-04

### Quick Wins: Newsletter Button Label and Cart State Indicator

Two single-file copy/css fixes that ship in one PR. The newsletter signup ends in an unlabelled arrow glyph that could be read as a `next step` indicator rather than a submit action — replace it with a labelled, full-width `Send me new-part drops` or `Join the list` button under the email input. The cart icon in the persistent header is a flat outlined glyph with no count badge, no dot, and no adjacent text — add a brand-orange numeric badge when item-count > 0 and consider a filled glyph plus a small `Cart` label.

Refs: visual-cta F-77, visual-cta F-11

## Findings by Cluster

### category-navigation cluster

### category-navigation F-05 — Search Bar Has No Fitment Binding

**SECTION:** header-nav
**ELEMENT:** `input.search` at e14 (combobox, 348px wide, sticky)
**SOURCE:** BOTH
**PRIORITY:** HIGH

**OBSERVATION:** The header search box accepts free-text queries with a `Search` placeholder and no fitment context. A shopper who types `cold air intake` gets every intake in the catalog, including parts that do not fit their Focus RS, ST, WRX, or STI. The Find Parts vehicle dropdown directly below proves the store has fitment data, but that data is not piped into the search experience.

**RECOMMENDATION:** Bind the search input to the visitor's selected vehicle: once Make/Model/Year/Trim is set in Find Parts, persist it (cookie or localStorage) and pre-filter all search results and autocomplete suggestions to fit-confirmed parts. Display the active vehicle as a removable chip inside the search bar (e.g., `Searching: 2018 Focus RS`) so the shopper can verify or clear the constraint. Rotate the placeholder through three concrete examples (`Try: Focus RS cold air intake`, `Try: WRX coilovers`, `Try: STI shift knob`) to coach query vocabulary at the same time.

**Why this matters:** Compatibility-dependent catalogs see roughly 65% task failure when shoppers cannot constrain results to their vehicle. On a four-platform parts store, every unfiltered search forces the shopper to manually verify fitment on the PDP, and most abandon before that step.

▸ search-and-filter-ux.md [Gold]

### category-navigation F-84 — Subcategory Carousel Has No Scroll Affordance

**SECTION:** subcategory-tiles
**ELEMENT:** `div.subcategory-carousel` at e8 (Performance tile only visible)
**SOURCE:** VISUAL
**PRIORITY:** HIGH

**OBSERVATION:** The five top-level subcategories — Performance, Handling & Brakes, Interior, Exterior, Electronics — render as a horizontal carousel with one full-width tile visible at a time. There are no pagination dots, no chevron arrow, and no peek of the next tile's edge to signal swiping reveals more categories. A shopper looking for exhaust parts has no way of knowing Performance is one of five tiles versus the only category that exists.

**RECOMMENDATION:** Restructure the row so the next tile peeks 8-16% into the viewport at rest, and add a dot pagination row underneath (5 dots, current dot filled). Better still on mobile: drop the carousel and render the five tiles as a 2-column grid (Performance/Handling, Interior/Exterior, Electronics spanning the third row) so all five subcategories are visible without interaction.

**Why this matters:** Subcategories are the primary self-routing tool on a homepage with thousands of SKUs. Hiding four of five categories behind an undiscovered swipe gesture forces every shopper through the hamburger menu or the vehicle selector, both of which add friction versus a one-tap category jump.

▸ merchandising-psychology.md [Silver]

### category-navigation F-45 — Featured Collection Renders One Card Per Row

**SECTION:** featured-collection
**ELEMENT:** `img.product-card` at e36 (266×266 in 390px viewport)
**SOURCE:** BOTH
**PRIORITY:** HIGH

**OBSERVATION:** The Featured Collection on mobile shows one product card occupying nearly the full viewport width (266px image in a 390px frame) with the second card peeking. The ecommerce mobile standard is a 2-column grid that surfaces 4-6 products per scroll — this layout shows 1-2 and consumes ~700 vertical pixels per product. A shopper has to swipe four times to see the same five products a 2-column grid renders in a single screen.

**RECOMMENDATION:** Switch the Featured Collection to a 2-column grid on mobile with consistent card heights (image aspect ratio 1:1, fixed title height 2 lines with ellipsis, price line, badge line). Reserve the wide-card carousel only for editorial `Build of the Month`-style merchandising blocks, not for browse-intent product surfaces.

**Why this matters:** Mobile shoppers form purchase shortlists by scanning rhythm; a 2-column grid lets them compare adjacent cards on price and image at a glance. A single-column carousel forces sequential evaluation, which slows browse and bias-loads the visible card with disproportionate attention.

▸ grid-layout.md [Silver]

### category-navigation F-04 — Lead Featured Card Missing Star Rating

**SECTION:** featured-collection
**ELEMENT:** `img.product-card` at e36 (lead VelourTex card, no star row)
**SOURCE:** BOTH
**PRIORITY:** MEDIUM

**OBSERVATION:** The lead Featured Collection card (VelourTex Floor Mats) renders with no star rating or review count, while the next card in the carousel (Revo Designs Rocker Stripes) shows a `5.0/5.0 (2)` rating with review count. The asymmetry suggests stars only render when the product has reviews, with no placeholder when the product has zero. The first impression card is therefore the weakest social-proof card on the page.

**RECOMMENDATION:** Always reserve the rating row in the card template. If the product has reviews, render the star graphic plus numeric rating plus count (`★★★★★ 5.0 (2)`). If the product has zero reviews, render a low-key `Be the first to review` link or a neutral `New arrival` badge so the row never collapses and the card layout stays consistent. Promote a higher-reviewed product into the lead Featured slot until floor mats accumulate ratings.

**Why this matters:** Spiegel/Northwestern shows up to 270% higher purchase likelihood when a product card carries even five reviews versus none. A blank rating row on the lead card cedes that lift, and the inconsistency between cards trains shoppers to discount the rating signal across the whole grid.

▸ product-cards.md [Gold]

### category-navigation F-87 — No View-All Exit on Featured Collection

**SECTION:** featured-collection
**ELEMENT:** `View All` link (absent — proposed location: after e34)
**SOURCE:** VISUAL
**PRIORITY:** MEDIUM

**OBSERVATION:** The Featured Collection heading announces a curated set, but there is no `View All` or `Shop the Collection` CTA accompanying the heading or terminating the carousel. A shopper interested in floor mats has to swipe through the carousel, find a related product, and click into the PDP to discover whether a category page even exists.

**RECOMMENDATION:** Add a `View All` link to the right of the Featured Collection heading (chevron `View all >`) and a terminal card at the end of the carousel (`See all 24 products in this collection →`). Both link to the underlying collection page so the shopper has two clear exits from the merchandised carousel into the full grid.

**Why this matters:** A featured carousel without a view-all exit is a dead-end merchandising surface — it shows what the merchant chose, then drops the shopper rather than promoting them to the broader catalog. Adding the exit lifts collection-page traffic, which is where filtering and sort actually happen.

▸ collection-page-architecture.md [Silver]

### category-navigation F-59 — No Persistent Vehicle Selector After Find Parts

**SECTION:** header-nav
**ELEMENT:** vehicle chip (absent — proposed location: after e25, sticky header secondary bar)
**SOURCE:** VISUAL
**PRIORITY:** HIGH

**OBSERVATION:** The Find Parts vehicle gate captures Make, Model, Year, and Trim, but nothing on the page footprint indicates the chosen vehicle persists across navigation. The sticky header carries only the logo, hamburger, profile, and cart icon. A shopper who picks 2018 Focus RS and lands on a category page has no visual confirmation the catalog is filtered, and clicking the logo back to the homepage requires re-selecting the vehicle.

**RECOMMENDATION:** Add a persistent vehicle chip to the sticky header — a thin secondary bar below the logo row reading `Shopping for: 2018 Focus RS [Change] [Clear]` — and persist the selection in localStorage so it reapplies on every page load. Render the same chip inside the hamburger drawer above the category list.

**Why this matters:** Year-Make-Model gates only earn their conversion lift when the captured fitment carries forward; without persistence, every back-button or logo click resets the filter and forces re-selection, training shoppers to abandon the gate entirely.

▸ search-and-filter-ux.md [Gold]

### category-navigation F-98 — Search Bar Visible at Top, Not Hidden Behind Icon

**SECTION:** header-nav
**ELEMENT:** `input.search` at e14 (348px wide, sticky-on-scroll)
**SOURCE:** VISUAL
**PRIORITY:** LOW

**OBSERVATION:** The search input is a visible 348px-wide field anchored at the top of the viewport and persists in the sticky header on scroll. This satisfies the NNGroup baseline for sites with more than 50 products and avoids the most common mobile search-discovery failure.

**RECOMMENDATION:** Keep the always-visible, sticky-on-scroll pattern. Remaining search-bar work is upstream — placeholder coaching and fitment binding (see F-05) — not the visibility surface.

**Why this matters:** An exposed search input doubles search-driven engagement compared to icon-toggled implementations, especially on mobile where extra taps cost disproportionately.

▸ search-and-filter-ux.md [Gold]

### visual-cta cluster

### visual-cta F-24 — Hero Lacks Headline And Value Proposition

**SECTION:** hero
**ELEMENT:** hero band (absent — proposed location: after e14, above vehicle picker)
**SOURCE:** VISUAL
**PRIORITY:** HIGH

**OBSERVATION:** Above the fold the visitor sees only a search bar, four empty `Select Make / Model / Year / Trim` dropdowns, and a `FIND PARTS` button overlaid on a stock Subaru WRX photograph. Nothing on the page tells a first-time visitor what AWDMods sells, who the parts are for, or why to buy here instead of from a generic parts marketplace. A 5-second comprehension test would fail Question 1 (`what does this site sell?`) because the words `parts`, `AWD`, and the vehicle-picker context do not add up to a value proposition without prior brand familiarity.

**RECOMMENDATION:** Add a one-line headline directly above the vehicle picker that names the offer in plain words, paired with a one-line subhead naming the audience. Example: headline `Performance parts for Focus RS, Focus ST, WRX and STI.` / subhead `Fitment-checked for your exact trim. Free shipping over $75.` This puts the 5-second-test answer on the screen for every cold visitor and gives the dropdown picker context.

**Why this matters:** Cold paid traffic and SEO entries arrive without brand context. With no headline, the page asks the visitor to learn the brand, infer the catalog, and operate a four-step picker before they have any reason to invest. Most bounce before the first dropdown opens.

▸ hero-section-psychology.md, Finding 1 [Gold]

### visual-cta F-36 — Find Parts Button Has Washed-Out Contrast

**SECTION:** hero
**ELEMENT:** `button.find-parts` (translucent blue fill, white label over white car body at y~740)
**SOURCE:** VISUAL
**PRIORITY:** HIGH

**OBSERVATION:** The single primary action on the page renders as a half-transparent blue panel sitting over the brightest section of the hero photograph, where the white headlights of the car bleed through the button fill. Looking at the screenshot, the word `FIND PARTS` and the magnifying-glass icon almost merge with the white car body behind them — the button reads as a fading rectangle, not as the most clickable thing on the page. The squint test for the hero collapses to `image of a car`, not `button`.

**RECOMMENDATION:** Make the FIND PARTS button a solid, opaque fill (the existing brand blue at 100% opacity, or the orange used elsewhere on the site for the quick-add badge). Add a 1-2px darker border or a subtle drop shadow so the button retains separation from any background image. Verify a 4.5:1 text-on-button contrast ratio per WCAG 2.2 across the full width of the button, not just the corners.

**Why this matters:** If the only conversion action above the fold is hard to see, the entire vehicle-picker funnel below it goes unused. Contrast is the single most-replicated lever in CTA testing — a button that fails the squint test will under-convert regardless of how well the form below it is designed.

▸ color-psychology.md, Finding 2 [Silver]

### visual-cta F-67 — No Sticky CTA After Hero Scrolls Off

**SECTION:** sticky-bar
**ELEMENT:** sticky CTA (absent — proposed location: viewport-bottom-sticky after primary CTA offscreen)
**SOURCE:** VISUAL
**PRIORITY:** HIGH

**OBSERVATION:** The vehicle picker and FIND PARTS button live only in the hero section. Once a mobile visitor scrolls past approximately y=810 to browse the category cards or featured products, the only way back to the picker is to scroll all the way to the top or open the hamburger menu. There is no sticky bottom bar, no minimised vehicle-picker chip, and no persistent `FIND PARTS for my car` affordance anywhere on the page.

**RECOMMENDATION:** Once the hero FIND PARTS button leaves the viewport, render a slim sticky bar across the bottom of the mobile screen with either (a) a single-tap `FIND PARTS for [Selected Vehicle]` button if the picker has been used, or (b) a `Pick your vehicle` button that scrolls back to or expands the picker drawer. Keep the bar under 56px tall to preserve content area; match the brand blue used in the hero so the action reads as the same primary CTA persisting downpage.

**Why this matters:** Multiple independent A/B tests show sticky mobile CTAs lifting completed actions in the 5-37% range. AWDMods' entire conversion funnel begins with vehicle selection, so losing access to that picker after the first screenful breaks the path on every product card and every category browsing scroll.

▸ cta-design-and-placement.md, Finding 11 [Silver]

### visual-cta F-04 — Quick-Add Plus Icon Lacks Textual Affordance

**SECTION:** featured-collection
**ELEMENT:** `button.quick-add` at e36 (orange square, white `+` glyph at corner)
**SOURCE:** BOTH
**PRIORITY:** MEDIUM

**OBSERVATION:** Each product card on the Featured Collection grid carries a single conversion action: an orange square with a white `+` glyph overlaid on the bottom-right corner of the product photo. There is no text label anywhere on the card telling a thumb-scrolling visitor what tapping that icon does — Add to Cart? Quick view? Wishlist? The card title (`LLOYD MATS / VELOURTEX FITTED CARPET FLOOR MATS`) and the `FROM $135.99` price are the only labelled elements; the action itself is unannotated.

**RECOMMENDATION:** Replace the `+` icon-only quick-add with a labelled, full-width button under the price that reads `Choose Options` (since these SKUs have variants — the `Made to Order` badge confirms configuration is required) or `Add to Cart` for fixed-variant SKUs. Keep the orange brand colour but make the button at minimum 48px tall and span the card width so the action is unambiguous and Fitts-friendly.

**Why this matters:** Icon-only CTAs on product cards consistently under-perform labelled buttons in commerce A/B tests because the action requires the visitor to learn the icon's meaning before tapping. On a homepage where these are the only purchase-path entries below the hero, every unrecognised icon is a lost click.

▸ cta-design-and-placement.md, Finding 6 [Silver]

### visual-cta F-69 — Featured Collection Heading Is Generic

**SECTION:** featured-collection
**ELEMENT:** `h2` at e34 (text: `Featured Collection`)
**SOURCE:** BOTH
**PRIORITY:** MEDIUM

**OBSERVATION:** The largest piece of typography between the hero and the product grid is the words `Featured Collection` — a generic Shopify default that names the layout, not the merchandise or the buyer. It tells a visitor nothing about what they are about to scroll through, who the products are for, or why these specific four items are surfaced first. A competitor could copy this heading verbatim and lose nothing.

**RECOMMENDATION:** Replace `Featured Collection` with a vehicle- or use-case-specific lead-in that previews what the grid contains, such as `New for Focus RS / ST owners` or `Top-rated upgrades this month`. If the grid is curated by the team, name the curator or the reason: `AWDMods picks for fall 2026`. Reserve the H2 weight for copy that gives the visitor a reason to read the four cards beneath it.

**Why this matters:** Generic platform-default headings get scanned past in milliseconds. On a mobile homepage where the visitor has already scrolled past a value-prop-free hero, this is the second chance to plant a reason to keep going — and the page spends it on the word `Featured`.

▸ headline-copywriting.md, Finding 1 [Silver]

### visual-cta F-77 — Newsletter Subscribe Button Is Icon-Only

**SECTION:** newsletter
**ELEMENT:** `button.newsletter-submit` at e78 (arrow glyph, ~46×49 px)
**SOURCE:** BOTH
**PRIORITY:** MEDIUM

**OBSERVATION:** The newsletter signup is the only conversion action in the lower third of the page, but its submit control is a bare arrow glyph at the end of the email field. The button has no word on it — no `Subscribe`, no `Sign me up`, no `Join` — and the arrow glyph could plausibly be read as a `next step` indicator rather than a submit action. Visually it competes with the surrounding outlined input rather than asserting itself as a button.

**RECOMMENDATION:** Replace the arrow-only button with a labelled, full-width button beneath the email input that reads `Send me new-part drops` or `Join the list`. First-person framing (`Send me…`, `Sign me up`) matches the testing pattern that has consistently lifted submit rates over second-person (`Subscribe`). Keep the orange brand accent so the button visually owns the section.

**Why this matters:** Email capture is the only action AWDMods can measure from visitors who don't yet have a vehicle in mind. An unlabelled arrow forces the visitor to guess what tapping it does and whether they are committing to anything; the result is a quieter list and weaker remarketing pool.

▸ cta-design-and-placement.md, Finding 4 [Gold]

### visual-cta F-52 — Category Card Buttons Sit Below Card Fold

**SECTION:** subcategory-tiles
**ELEMENT:** `div.category-tile` at e8 (Performance card visible y=900-1500, button at y~1490)
**SOURCE:** BOTH
**PRIORITY:** MEDIUM

**OBSERVATION:** The category-card carousel below the hero shows only one full card per mobile screen with a sliver of the next card at the right edge. The `SHOP PERFORMANCE` button on the visible card sits low — bottom of the card around y=1490 — meaning a visitor who only ever sees the hero plus one screenful of below-fold content reaches at most one of five category buttons without intentional horizontal swiping. There is no visible swipe affordance (no dot pagination at the section bottom, no edge fade) cuing that more cards exist.

**RECOMMENDATION:** Either (a) collapse the five categories into a 2-column grid that shows all five labels above the fold-plus-one without horizontal scrolling, with each tile reading `Shop [Category]` as a tap target, or (b) add a visible pagination dot indicator and arrow chevron at the right edge so the swipe affordance is obvious. The current single-card-per-screen layout hides four of five primary navigation paths.

**Why this matters:** On a homepage where the hero tells the visitor nothing about the catalog, the category tiles are the next-best discovery surface. Hiding four of the five behind an undiscoverable horizontal swipe collapses the homepage's wayfinding to a single vertical scroll past `Performance`.

▸ eye-tracking-and-scan-patterns.md, Finding 4 [Gold]

### visual-cta F-11 — Cart Icon Has No State Indicator

**SECTION:** header-nav
**ELEMENT:** `button.cart` at e6 (outlined glyph, no badge, ~46×46 px)
**SOURCE:** BOTH
**PRIORITY:** LOW

**OBSERVATION:** The cart icon in the persistent header is a flat outlined glyph with no count badge, no dot, no colour change, and no adjacent text. There is no visual signal at any scroll depth telling the visitor whether their cart is empty, has items, or has unsaved changes from a prior session.

**RECOMMENDATION:** Add a small numeric badge in the brand orange to the cart icon when item-count is greater than zero, and consider replacing the empty-state outline with a filled glyph plus a small `Cart` label beneath it on mobile. Keep the badge legible at 44px and ensure tap target remains at least 44×44 per Apple HIG.

**Why this matters:** Without a state indicator, returning visitors who already have items in cart get no nudge to complete checkout — they have to tap the icon just to see whether anything is there. A visible count badge is one of the highest-leverage micro-CTAs on a Shopify storefront.

▸ cta-design-and-placement.md, Finding 5 [Silver]

## Methodology Notes

Two clusters audited (visual-cta, category-navigation) plus an ethics gate. One ADJACENT ethics finding (Privacy Policy staging-domain link). Page is the AWDMods storefront homepage at 390×844 mobile viewport.
