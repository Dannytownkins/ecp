# ECP Audit — Mobile

**Engagement:** 2026-05-03-awdmods-pdp  
**URL:** https://www.awdmods.com/products/ford-focus-rs-borla-atak-exhaust-system?variant=43272042840129  
**Page type:** Product page  
**Viewport:** mobile  
**Clusters audited:** visual-cta, trust-credibility, pricing, content-seo

## Priority Path

1. **Compress the mobile buying path.** The first viewport is mostly header and product media, while price and CTA require scroll. Add a sticky add-to-cart bar and reduce top chrome/media height.
2. **Make the CTA state obvious.** The button says "SELECT COLOR" even with a visible selected option, which reads as an unresolved setup step.
3. **Move trust and cost certainty into the purchase zone.** Reviews, fitment, shipping eligibility, returns/warranty, and payment trust are missing from the decision area.

## Findings

### visual-cta cluster

```
FINDING: FAIL
TITLE: Mobile Add-to-Cart Is Below the First Viewport
SECTION: mobile-cta
ELEMENT: #ProductSubmitButton-template--20109859586113__main
SOURCE: BOTH
OBSERVATION: On mobile, the first viewport shows the promo bar, header, search, product image, thumbnails, title, color selector, and price, but the purchase button is not visible until the next scroll position. The button sits around 902 CSS px from the top on an 844 CSS px viewport.
RECOMMENDATION: Add a compact sticky bottom purchase bar that appears once the shopper scrolls past the product media. Include selected color, price, and "Add to Cart." Also reduce mobile header/search height or media height so the purchase path appears sooner.
REFERENCE: cta-design-and-placement.md:Finding 11
PRIORITY: HIGH
**Why this matters:** Sticky mobile PDP CTAs have repeatedly lifted add-to-cart and completed-order metrics because the action remains available while shoppers evaluate content.
↳ cta-design-and-placement.md, Finding 11 (Blend Commerce; GrowthRock) [Bronze]
```

```
FINDING: FAIL
TITLE: CTA Says Select Color After Color Is Already Selected
SECTION: cta-copy
ELEMENT: #ProductSubmitButton-template--20109859586113__main
SOURCE: BOTH
OBSERVATION: The mobile page shows "Polished Tips" selected, but the primary CTA says "SELECT COLOR." This creates the impression that the page is blocked or the selected option was not accepted.
RECOMMENDATION: When a valid variant is selected, change the CTA to "Add to Cart - $1,649.99" or "Add Polished Tips to Cart." If another required selection is missing, put the exact missing action above the button.
REFERENCE: cta-design-and-placement.md:Finding 14
PRIORITY: HIGH
**Why this matters:** Specific action labels reduce uncertainty; generic or mismatched labels make shoppers spend effort interpreting the UI instead of buying.
↳ cta-design-and-placement.md, Finding 14 (Nielsen Norman Group) [Gold]
```

```
FINDING: PARTIAL
TITLE: Header and Search Consume Too Much Mobile Buying Space
SECTION: mobile-scroll
ELEMENT: header.header.header--top-left
SOURCE: VISUAL
OBSERVATION: The mobile header plus promo/search area takes roughly the top 180 CSS px before the product content begins. That pushes title, price, and CTA lower and makes the first viewport feel like navigation rather than a product decision screen.
RECOMMENDATION: Collapse the search bar after initial load, make it an icon-triggered overlay, or reduce its vertical padding on PDPs. Preserve search access, but prioritize product title, price, and action.
REFERENCE: cta-design-and-placement.md:Finding 12
PRIORITY: MEDIUM
**Why this matters:** Visual isolation and reduced competing chrome help the primary action area get seen sooner.
↳ cta-design-and-placement.md, Finding 12 (VWO/Open Mile composite test) [Bronze]
```

### trust-credibility cluster

```
FINDING: FAIL
TITLE: High-Ticket Mobile PDP Has No Visible Reviews Before Purchase
SECTION: reviews-display
ELEMENT: div.product__title + price area
SOURCE: BOTH
OBSERVATION: The mobile purchase path shows title, color, price, BNPL, quantity, and CTA, but no star rating, review count, verified-buyer badge, or "read reviews" anchor before the shopper reaches the button.
RECOMMENDATION: Add a compact star/review row under the title. If product-specific reviews are unavailable, show honest category or brand review context separately and prioritize post-purchase review collection for this SKU.
REFERENCE: trust-and-credibility.md:Finding 4
PRIORITY: HIGH
**Why this matters:** Expensive products rely more heavily on social proof; review absence increases perceived purchase risk.
↳ trust-and-credibility.md, Finding 4 (Spiegel Research Center, Northwestern University, 2017) [Gold]
```

```
FINDING: PARTIAL
TITLE: Fitment Assurance Is Not Tied to the Buy Button
SECTION: trust-above-fold
ELEMENT: #ProductInfo-template--20109859586113__main
SOURCE: VISUAL
OBSERVATION: The page eventually shows specifications for Make, Model, Year, Trim, and Part Number, but the mobile CTA area does not summarize fitment or inclusion confidence before purchase.
RECOMMENDATION: Add a short trust strip above or below the CTA: "Fits 2016-2018 Focus RS," "Hardware + instructions included," "Secure checkout," and "Returns/warranty details." Link to the specification accordion.
REFERENCE: benefit-first-descriptions.md:Finding 2
PRIORITY: MEDIUM
**Why this matters:** Complex automotive products need enough compatibility detail on the PDP to prevent users from leaving to verify elsewhere.
↳ benefit-first-descriptions.md, Finding 2 (NNGroup; Baymard Institute) [Gold]
```

### pricing cluster

```
FINDING: PARTIAL
TITLE: Free Shipping Eligibility Is Not Confirmed on the Product
SECTION: shipping-cost-display
ELEMENT: promo bar + product price area
SOURCE: VISUAL
OBSERVATION: The global promo says "FREE SHIPPING on most orders $75+ -- Contiguous US only," but the product area does not confirm whether this $1,649.99 exhaust qualifies or whether oversized shipping exceptions apply.
RECOMMENDATION: Add a product-level line near the price: "Qualifies for free contiguous-US shipping" or "Oversized shipping calculated at checkout." The wording must reflect actual fulfillment rules.
REFERENCE: free-shipping.md:Finding 2
PRIORITY: HIGH
**Why this matters:** Unexpected extra costs are a leading controllable cart-abandonment driver, especially when the item is physically large.
↳ free-shipping.md, Finding 2 (Baymard Institute) [Gold]
```

```
FINDING: PARTIAL
TITLE: BNPL Message Is Visible but Not Anchored to Value Confidence
SECTION: price-framing
ELEMENT: shop-pay installment line
SOURCE: VISUAL
OBSERVATION: The BNPL line appears before the CTA, but it does not sit beside shipping, return, warranty, or fitment confidence. On mobile it becomes a large line item without explaining why this $1,649 part is safe to finance.
RECOMMENDATION: Keep the installment price near the product price, but pair it with full-price clarity, shipping eligibility, and returns/warranty links. Do not let BNPL become the only confidence cue.
REFERENCE: bnpl-payment.md:Finding 4
PRIORITY: MEDIUM
**Why this matters:** BNPL works best when installment awareness appears before purchase, but responsible display should preserve total-cost and trust clarity.
↳ bnpl-payment.md, Finding 4 (CFPB; merchant implementation data) [Silver]
```

```
FINDING: PARTIAL
TITLE: Compare-At Price Lacks a Savings Explanation
SECTION: price-anchoring
ELEMENT: div.price.h3-size
SOURCE: BOTH
OBSERVATION: Mobile shows the sale price and crossed-out regular price, but not the savings amount, percent, or anchor source. The shopper sees that the product is discounted but not why the anchor is credible.
RECOMMENDATION: Add "Save $198 (11%) vs. MSRP" if true, or label the anchor honestly as "Was." If the original price is not defensible, remove the crossed-out anchor.
REFERENCE: pricing-psychology.md:Finding 1
PRIORITY: MEDIUM
**Why this matters:** Anchors influence value perception, but unexplained anchors can weaken trust when the product is expensive.
↳ pricing-psychology.md, Finding 1 (Tversky & Kahneman; Ariely et al.) [Gold]
```

### content-seo cluster

```
FINDING: FAIL
TITLE: Mobile Product Title Is Not the Page H1
SECTION: value-proposition
ELEMENT: div.product__title h2.b-main-title.h3
SOURCE: CODE
OBSERVATION: The captured DOM contains no H1. The visible product title is rendered as H2, even though it is the main product heading.
RECOMMENDATION: Render the product title as the single H1 for the PDP. Keep the same typography if desired; change the semantic element.
REFERENCE: title-formulas-serp-psychology.md
PRIORITY: HIGH
**Why this matters:** The main heading should clearly identify the product for users, assistive technology, and search engines.
```

```
FINDING: FAIL
TITLE: Product Copy Has Visible Typos in the Purchase Path
SECTION: value-proposition
ELEMENT: div.content-truncator__content.product__description
SOURCE: BOTH
OBSERVATION: The mobile PDP description includes errors such as "so would this would" and "thst." The copy also leads with repeated product phrasing before the actual buyer benefits.
RECOMMENDATION: Rewrite the first paragraph around the outcome: Borla ATAK sound, bolt-on Focus RS fitment, stainless construction, included hardware/instructions, and available tip finishes. Put detailed specs below that benefit-led opening.
REFERENCE: benefit-first-descriptions.md:Finding 1
PRIORITY: HIGH
**Why this matters:** Premium-product copy must build confidence quickly; typos and repetition reduce perceived brand value.
↳ benefit-first-descriptions.md, Finding 1 (Levitt; Christensen) [Silver]
```

```
FINDING: PARTIAL
TITLE: Product Schema Needs Merchant Listing Enhancements
SECTION: value-proposition
ELEMENT: script[type="application/ld+json"]
SOURCE: CODE
OBSERVATION: The page has Product JSON-LD with offers, price, availability, SKU, and brand. It does not include aggregateRating/review data, shippingDetails, MerchantReturnPolicy, or ProductGroup variant structure for the two tip finishes.
RECOMMENDATION: Extend the JSON-LD with accurate reviews when available, shipping details, return policy, and ProductGroup/hasVariant markup for Polished Tips and Carbon Fiber Tips. Keep this synchronized with Shopify and Merchant Center.
REFERENCE: schema-product-markup.md:Finding 5
PRIORITY: MEDIUM
**Why this matters:** Variant and merchant-listing metadata helps Google and AI shopping surfaces understand purchasable options, policies, and trust details.
↳ schema-product-markup.md, Finding 5 (Google Search Central) [Gold]
```
