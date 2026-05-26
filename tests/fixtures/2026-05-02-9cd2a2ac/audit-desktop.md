# Audit — AWDMods Homepage (desktop)

## Executive Summary

The desktop homepage hides its highest-leverage navigation lever — vehicle fitment — behind a small header pill and a low-contrast hero overlay, while the hero itself ships no headline, no value proposition, and no primary CTA. The Featured Collection grid below renders eight of ten cards without star ratings and stamps every card with the same "Made to Order" badge, neutralizing the homepage's main social-proof and merchandising signals. Start with the hero (headline + Find Parts CTA + trust strip), then fix the Featured Collection card template.

## Ethics Gate

One ADJACENT finding: the footer Privacy Policy link points to a `myshopify.com` staging-domain host instead of the canonical storefront. Disclosure exists, but the chain-of-disclosure is fragile and a one-line config fix.

## Top Priorities

### Promote Vehicle Fitment to a Persistent Above-Fold Selector

The fitment selector is the single highest-leverage control on a four-platform parts catalog (Focus RS, Focus ST, WRX, STI), yet desktop renders it as a small "SELECT YOUR VEHICLE" pill in the top-right header — smaller than the cart icon — plus a low-contrast "Select Make" dropdown floating over the hero photo that exposes only one of the three required steps. The header search input (929px wide) dominates the same band, inverting the friction: visitors who do not yet know an exact part name type a guess, get unfiltered results, and either bounce or buy a wrong-fitment SKU. Promote a full-width Year/Make/Model strip directly under the primary header with all three dropdowns visible at rest, and shrink the search to a smaller right-aligned input. The placeholder on the remaining search input should template a fitment example (`Try "2018 WRX cold air intake"`) so the catalog reads as fitment-aware from the first scan.

Refs: category-navigation F-19, category-navigation F-03, visual-cta F-89

### Rebuild the Hero with Headline, Value Prop, Primary CTA, and Trust Strip

The hero band renders a full-bleed WRX photograph with zero overlaid copy — no headline, no subhead, no filled CTA — and no above-fold credibility marker. The five blue category buttons below the hero compete equally with one another, none promoted as the page's primary commit. Add an H1 naming the buyer and offer (`Performance Parts for Subaru WRX, STI, Ford Focus RS and ST`), a one-line subhead naming the differentiator, a single filled `Find Parts For My Car` CTA at minimum 200×55 in the existing brand blue, and a slim trust strip immediately under the header carrying aggregate review rating, Authorized Dealer call-out, and a Fitment Guaranteed line. Demote the five SHOP-X buttons to a secondary row so the hero resolves to one primary action.

Refs: visual-cta F-12, visual-cta F-37, visual-cta F-38, visual-cta F-13

### Restore the Featured Collection's Merchandising and Social-Proof Signals

The Featured Collection is the homepage's primary product surface and is currently doing the opposite of merchandising work: eight of ten cards render with no star rating row, every card carries an identical yellow `Made to Order` badge, and the heading is text-only with no `View all` link. The two cards that do show ratings (`5.0 (2)`) prove the template supports the field — it is simply absent on cards whose products have zero or unfetched reviews. Render the rating row on every card (use `No reviews yet` for zero-review products so card heights stay consistent), reserve badges for genuine differentiation (`Best Seller`, `New`, `Low Stock`) and move the `Made to Order` label into the card body near the price as logistics copy, and add a `Shop the collection →` link aligned right of the `Featured Collection` heading.

Refs: category-navigation F-51, category-navigation F-28, category-navigation F-06

### Drop the Featured Grid from Five Columns to Four at 1920px

At the 1920px breakpoint the Featured Collection renders five product columns at 271×271 — at the published ceiling for grid density and the wrong choice for an automotive parts context where shoppers need to distinguish parts by shape and finish. Drop to four columns at ≥1440px and let cards grow to ~325px wide. Reserve five-column density for the full collection page where users have already committed to a category.

Refs: category-navigation F-96, category-navigation F-51

## Findings by Cluster

### category-navigation cluster

### category-navigation F-19 — Vehicle Fitment Selector Buried as Tertiary CTA

**SECTION:** header-nav
**ELEMENT:** `SELECT YOUR VEHICLE` header pill (absent baton — proposed location: after e23, full-width strip below search)
**SOURCE:** VISUAL
**PRIORITY:** HIGH

**OBSERVATION:** Visitors arriving at AWDMods need to confirm a part fits a specific Subaru WRX, STI, Ford Focus RS or ST before any browse decision matters. The site's two fitment entry points — the `SELECT YOUR VEHICLE` pill in the top header and the `Select Make` dropdown floating over the hero photo — are both visually subordinate. The header pill is smaller than the cart icon and competes with the search bar for attention; the hero dropdown sits on a busy automotive background with insufficient contrast and exposes only one of the three required fitment steps (Make, with no visible Year or Model controls until interaction).

**RECOMMENDATION:** Promote the Year/Make/Model selector to a full-width persistent strip directly under the primary header, with all three dropdowns visible in their resting state (Year, Make, Model, Submodel where applicable). Treat it as the page's primary conversion lever rather than as a header utility. On the hero, replace the floating `Select Make` fragment with a single `Find parts for your car` CTA that scrolls focus into the header strip.

**Why this matters:** Baymard's compatibility-filter study found only 35% of visitors successfully complete a purchase task on parts sites that hide or under-weight fitment selection. For an aftermarket parts catalog where wrong-fit returns are costly and trust-damaging, fitment is the single highest-leverage navigation element on the page.

▸ search-and-filter-ux.md, Finding 5 (Baymard) [Gold]

### category-navigation F-51 — Featured Grid Cards Missing Review Counts

**SECTION:** featured-collection
**ELEMENT:** `img.product-card` at e15 (y=980, height=271 CSS px)
**SOURCE:** BOTH
**PRIORITY:** HIGH

**OBSERVATION:** Eight of ten Featured Collection cards in the visible grid render with no star rating and no review count below the price. The two cards that do show rating data (a `5.0 (2)` tally on the carbon fiber peel-and-stick card) prove the template supports the field — it is simply absent on cards whose underlying products have zero or unfetched reviews. The page makes the homepage's most prominent shelf depend on bare title + price decisions.

**RECOMMENDATION:** Render the rating row on every card. For products with reviews, show the star graphic, numeric rating, and parenthetical count (`5.0 (2)`). For products with zero reviews, show a muted `No reviews yet` line in the same vertical slot so card heights stay consistent and the absence reads as data rather than as a missing UI element. If the catalog has Judge.me or Yotpo running site-wide, surface aggregate ratings from those services rather than only Shopify-native review counts.

**Why this matters:** Spiegel/Northwestern observed a 270% purchase-likelihood lift between products with zero reviews and products with five reviews. On a Featured Collection that is the homepage's primary discovery surface, missing the rating row on most cards forfeits the cheapest social-proof signal on the page and drives visitors back to the search bar.

▸ product-cards.md, Finding 1 (Spiegel/Northwestern) [Gold]

### category-navigation F-28 — Made to Order Badge Repeated on Every Card

**SECTION:** featured-collection
**ELEMENT:** `span.badge` at e51 (y=980)
**SOURCE:** BOTH
**PRIORITY:** MEDIUM

**OBSERVATION:** The `Made to Order` badge appears identically on every card in the Featured Collection grid (e51, e52, e53, e54, e55). Badges work as merchandising signals because they pick out one or two cards as different from the rest; when the same badge sits on every card it stops carrying information and becomes visual noise that crowds the price and title.

**RECOMMENDATION:** Reserve badges for genuine differentiation — `Best Seller` on the top-3 sellers, `New` on items added in the last 30 days, `Low Stock` when fewer than 5 units remain. Move the `Made to Order` label out of the badge slot and into the card body near the price (`Ships in 3–5 days, made to order`), where it carries logistics meaning without consuming the merchandising channel. Cap visible badges at one per card.

**Why this matters:** When every card flashes the same badge, visitors lose the scanning cue that lets them quickly find the bestseller, the new arrival, or the deal — the homepage stops doing the merchandising work it exists to do, and the burden shifts back to slow per-card title reading.

▸ product-cards.md, Finding 7 [Silver]

### category-navigation F-96 — Featured Grid Pushed to 5 Columns at 1920px

**SECTION:** featured-collection
**ELEMENT:** `div.product-grid` at e15 (y=980, card image 271×271 CSS px)
**SOURCE:** VISUAL
**PRIORITY:** MEDIUM

**OBSERVATION:** The Featured Collection grid renders five product columns at the 1920px breakpoint. Five columns sits at the published ceiling — Jenkins 2020 measured a 35% increase in scanning time when grids step from four to five columns, and small-image cards make subtle differences between, for example, two carbon-fiber trim pieces harder to register at a glance.

**RECOMMENDATION:** If the Featured Collection's role is curated discovery rather than full-catalog browse, drop to four columns at ≥1440px and let the cards grow to ~325px wide. Reserve five-column density for the full collection page where users have already committed to a category and are scanning for a specific part.

**Why this matters:** Slower grid scanning on the homepage's primary product surface translates directly into more visitors abandoning before they reach a product detail page, because the homepage's job is to hand off to a PDP within a few seconds of arrival.

▸ grid-layout.md, Finding 1 [Silver]

### category-navigation F-03 — Search Placeholder Misses Fitment Query Pattern

**SECTION:** header-nav
**ELEMENT:** `input.search` at e23 (y=20, 929×55 CSS px)
**SOURCE:** BOTH
**PRIORITY:** MEDIUM

**OBSERVATION:** The header search bar is well-sized and prominent — 929px wide, centered, with the search icon on the left — but its placeholder reads `What are you looking for?` Visitors arriving from a Google query for a specific part have no indication of what query syntax actually returns useful results on this catalog. They cannot tell whether the search will accept a year + model + part term, a part number, or only product titles.

**RECOMMENDATION:** Replace the generic placeholder with a templated example that seeds the right mental model, e.g. `Try "2018 WRX cold air intake" or part #`. Rotate the example through the four primary platforms (Focus RS, Focus ST, WRX, STI) on each page load so visitors quickly learn the catalog is fitment-aware.

**Why this matters:** NNGroup's search-bar guidance treats the placeholder as the primary discovery cue for first-time visitors. On a niche catalog, a generic placeholder forces users to guess at query syntax — the cheapest fix here moves the search from a hopeful-string entry into a guided fitment lookup.

▸ search-and-filter-ux.md, Finding 17 [Gold]

### category-navigation F-06 — Featured Collection Lacks View All Affordance

**SECTION:** featured-collection
**ELEMENT:** `h2` at e8 (text: `Featured Collection`)
**SOURCE:** BOTH
**PRIORITY:** MEDIUM

**OBSERVATION:** The Featured Collection heading is text-only — no inline `View all featured products` link sits to its right. The `There's plenty more...` tile at the end of the grid does carry a CTA, but visitors who decide they want the full collection while looking at the first row have no header-level escape to it.

**RECOMMENDATION:** Add a `View all` or `Shop the collection →` link aligned right of the `Featured Collection` heading, linking to the underlying Shopify collection URL. Keep the trailing `There's plenty more...` tile for visitors who scroll the row, but give early-decision visitors the same hand-off without forcing them to scroll past every card.

**Why this matters:** Heading-aligned `View all` links are also an SEO win — they expose a crawlable internal link to the full collection from the homepage, which collection-page-architecture treats as a trust signal in Google's category-page surfacing.

▸ collection-page-architecture.md, Finding 4 [Gold]

### category-navigation F-12 — Subcategory Tile Row Routes Visitors by Build Goal

**SECTION:** subcategory-tiles
**ELEMENT:** `div.subcategory-tile` at e17 (273×302 CSS px)
**SOURCE:** VISUAL
**PRIORITY:** LOW

**OBSERVATION:** The five-tile subcategory row immediately below the hero gives visitors a clean self-routing surface organized by build intent (Performance, Handling, Interior, Exterior, Electronics). Each tile names its subcategories inline (Intakes, Exhaust, Cooling, Drivetrain) so a visitor can choose the right path without hovering a mega-menu.

**RECOMMENDATION:** Keep this pattern. When the subcategory row is rebuilt for new product lines, preserve the inline subcategory naming and the per-tile CTA — both are doing real navigation work.

**Why this matters:** Subcategory tiles above the grid let visitors with a clear build goal ("I want exhaust") skip past the hero noise and land on a relevant subcategory in one click rather than three.

▸ merchandising-psychology.md, Finding 8 [Silver]

### visual-cta cluster

### visual-cta F-12 — Hero Has No Headline or Value Proposition

**SECTION:** hero
**ELEMENT:** hero band (absent — proposed location: before e23, overlaid on hero photograph)
**SOURCE:** VISUAL
**PRIORITY:** HIGH

**OBSERVATION:** The hero band on awdmods.com presents a full-bleed photograph of a tuned car but renders zero headline copy. A first-time visitor sees a navigation strip, a search box, and a tiny `SELECT YOUR VEHICLE` link — no statement of what the store sells, who it serves, or why a buyer should choose AWDMods over a competitor. The 5-second test fails: a visitor would have to read the navigation labels and infer the category from the car photograph to understand this is a performance-parts store for AWD vehicles.

**RECOMMENDATION:** Add a single H1 headline overlaid on the hero photograph naming the buyer and the proof point — for example, `Performance Parts for Subaru WRX, STI, Ford Focus RS and ST`. Keep it 6-12 words, place it left of center over the darkest area of the photograph for contrast, and pair it with a one-line subheadline naming the differentiator (fitment-verified, free shipping over $75, in-house support). The current `SELECT YOUR VEHICLE` micro-link should sit beneath this headline, not replace it.

**Why this matters:** Cold paid traffic, organic search visitors landing on the homepage, and even returning shoppers form a yes-or-no decision in the first 5 seconds. Without a headline naming the audience and the value, this hero converts only visitors who already know the brand — every other arrival has to do the cognitive work of decoding the page from photograph and navigation alone, and most leave.

▸ hero-section-psychology.md, Finding 1 [Silver]

### visual-cta F-37 — No Primary CTA Button in Hero

**SECTION:** hero
**ELEMENT:** primary CTA (absent — proposed location: hero section, beneath new headline)
**SOURCE:** BOTH
**PRIORITY:** HIGH

**OBSERVATION:** The hero band offers no single dominant call-to-action. The vehicle picker (`SELECT YOUR VEHICLE / Car parts, simplified`) is rendered as small text in the top-right corner, easy to overlook against the busy photograph. The five category buttons (`SHOP PERFORMANCE`, `SHOP HANDLING`, `SHOP INTERIOR`, `SHOP EXTERIOR`, `SHOP ELECTRONICS`) compete equally with one another below the hero — no one of them is positioned as the page's primary commit.

**RECOMMENDATION:** If the vehicle picker is the intended primary action (it is the highest-leverage filter for fitment-driven parts), promote it: render `Find Parts For My Car` as a filled blue button at least 200×55 in the same blue used on the category cards, placed under the new headline inside the hero photograph. Demote the five category-card buttons to a secondary row OR remove them from the immediate above-fold so the eye lands on a single conversion path.

**Why this matters:** Without a primary CTA, the hero leaves the visitor to choose from four competing entry points: type a search, click the small vehicle picker, scroll to a category card, or use the top-nav menu. Each added choice fragments attention and depresses the click-through rate of every option — the Whirlpool single-CTA test showed 42 percent lift from removing competing CTAs at exactly this commitment point.

▸ cta-design-and-placement.md, Finding 9 [Silver]

### visual-cta F-38 — No Above-Fold Trust Signal

**SECTION:** hero
**ELEMENT:** trust strip (absent — proposed location: after e24, between header and hero photograph)
**SOURCE:** VISUAL
**PRIORITY:** MEDIUM

**OBSERVATION:** The above-fold band carries no credibility marker — no aggregate star rating, no customer count, no Trustpilot or Google review badge, no Authorized Dealer call-out for the brands AWDMods carries, no fitment-guarantee statement. The first review evidence on the page is the `5.0 / 5.0 (2 reviews)` marker on a featured product (e45) which only appears at scroll position 1364, below the fold. Visitors evaluating a high-consideration purchase (Borla cat-back exhausts at $1,549.99, AEM intakes at $403.40) form their first credibility judgment from the hero alone.

**RECOMMENDATION:** Insert a slim trust strip directly beneath the header, above the hero photograph. Three to four marks works: aggregate review rating with count (`4.8 over 1,200+ reviews`) sourced from the existing Yotpo or Shopify reviews integration, an Authorized Dealer line listing two or three of the marquee brands carried (Borla, AEM, COBB), a `Fitment Guaranteed` line, and an `Easy Returns` or `30-Day Return` line. Keep the strip under 60 pixels tall so it does not push the hero photograph below the fold.

**Why this matters:** 57 percent of desktop viewing time is spent above the fold, so the credibility evidence the visitor sees there does most of the work of the page's trust posture. With zero trust signal in the hero, every visitor must scroll down through the categories and into the featured collection before they encounter the first proof point — a high-friction journey that price-sensitive performance-parts buyers will not complete.

▸ hero-section-psychology.md, Finding 10 [Silver]

### visual-cta F-13 — Five Equal-Weight Category CTAs Compete

**SECTION:** subcategory-tiles
**ELEMENT:** `div.category-card-row` at e17 (y=746-786, 5 buttons identical weight)
**SOURCE:** BOTH
**PRIORITY:** MEDIUM

**OBSERVATION:** The category-card row presents five identical filled-blue buttons with no visual hierarchy. Performance is almost certainly the highest-revenue category for an automotive performance store — intakes, exhaust, and turbo upgrades carry larger basket sizes and higher attach rates than Interior or Electronics — but its button reads at exactly the same visual weight as Electronics. The squint test confirms the issue: blur the row and five identical rectangles remain.

**RECOMMENDATION:** Either elevate one card as the lead path (larger card footprint, brighter accent, leading position with a `Most Popular` or `Best Sellers` tag on Performance) or, on a homepage, rank the five by revenue contribution and reduce the secondary categories to ghost or text-link styling. The merchandising team should pick one approach based on internal data; the current configuration is the worst case (five equal commits, none promoted).

**Why this matters:** When five conversion paths share equal visual weight, the visitor pays a small attention tax to scan all five and then makes a probabilistic choice — which usually means clicking nothing and continuing to scroll. A clear primary card concentrates traffic on the highest-margin path and reduces decision fatigue at the moment of intent.

▸ cta-design-and-placement.md, Finding 9 [Silver]

### visual-cta F-89 — Search Input Dominates Above-Fold Real Estate

**SECTION:** header-nav
**ELEMENT:** `input.search` at e23 (929×55 CSS px, center-left)
**SOURCE:** BOTH
**PRIORITY:** MEDIUM

**OBSERVATION:** The header allocates a 929-pixel-wide search bar to the center-left zone — the area that receives 80 percent of left-half fixations on desktop — while the vehicle-fitment picker (the action that filters the catalog to in-fitment parts and prevents return-rate-driving wrong-fitment purchases) is buried in the upper-right corner as small text. Search is a useful path for visitors who already know the part name, but vehicle selection is the higher-leverage entry for the larger audience that knows the car but not the SKU.

**RECOMMENDATION:** Either swap the dominance — promote the vehicle-fitment picker to a 600-700px wide visual block in the center of the header with the year/make/model selectors visible by default, and shrink the search to a smaller right-aligned input — or merge the two so the vehicle picker is the primary path and search becomes the secondary text-input within the same element.

**Why this matters:** On a fitment-driven parts catalog, wrong-fitment purchases drive returns, support tickets, and chargebacks — every order that ships against the wrong vehicle is a cost. Putting the fitment picker at low visual weight while the free-text search dominates inverts the friction: visitors who do not yet know the exact part name will type a guess, get unfiltered results, and either bounce or buy a wrong-fitment SKU.

▸ eye-tracking-and-scan-patterns.md, Finding 5 [Silver]

### visual-cta F-39 — Top Promo Bar Buries Free Shipping Threshold

**SECTION:** header-promo
**ELEMENT:** top promo ribbon (absent baton — top of page, thin blue bar)
**SOURCE:** VISUAL
**PRIORITY:** LOW

**OBSERVATION:** The free-shipping threshold — a real and meaningful offer for a category where the typical $135-$1,500 SKU comfortably crosses the $75 minimum — is rendered in the page's least-attention zone: a thin promotional ribbon at the very top, in small text against a saturated blue bar that mimics the ad-banner format. Three decades of banner-blindness research show this format is reliably ignored.

**RECOMMENDATION:** Either move the free-shipping line into the new trust strip recommended in F-38 (placed beneath the header), so it earns above-fold reading attention, or pair it with a per-product progress indicator on the PDP. Keep the top promo ribbon for genuinely time-bounded promotions (`Memorial Day Sale ends Monday`) where the banner-style is appropriate.

**Why this matters:** Free-shipping thresholds drive average order value when visitors see them early enough to add a second item. Buried in banner-blindness real estate, the offer is doing none of that work — the visitor only encounters the threshold after they have already added one item and opened the cart.

▸ eye-tracking-and-scan-patterns.md, Finding 6 [Silver]

## Methodology Notes

Two clusters audited (visual-cta, category-navigation) plus an ethics gate. One ADJACENT ethics finding (Privacy Policy staging-domain link). Page is the AWDMods storefront homepage — collection-page surfaces (filter panel, sort, pagination) were not in scope and would benefit from a follow-up audit on `/collections/wrx-performance` or similar.
