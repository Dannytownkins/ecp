# ECP Audit — Desktop

**Engagement:** 2026-05-03-awdmods-pdp  
**URL:** https://www.awdmods.com/products/ford-focus-rs-borla-atak-exhaust-system?variant=43272042840129  
**Page type:** Product page  
**Viewport:** desktop  
**Clusters audited:** visual-cta, trust-credibility, pricing, content-seo

## Priority Path

1. **Make the purchase module decisive.** Fix the misleading CTA label, strengthen the CTA contrast, and clarify whether the selected variant can be added to cart.
2. **Add high-ticket confidence signals near the price.** Put reviews, fitment assurance, returns/warranty, shipping eligibility, and payment trust directly beside the decision area.
3. **Clean up the PDP content and search metadata.** The page currently has no H1, typo-heavy description copy, and product metadata that omits review/return/shipping enhancement fields.

## Findings

### visual-cta cluster

```
FINDING: FAIL
TITLE: CTA Reads Like a Setup Step After a Variant Is Selected
SECTION: cta-copy
ELEMENT: #ProductSubmitButton-template--20109859586113__main
SOURCE: BOTH
OBSERVATION: The product has "Polished Tips" visibly selected, but the primary purchase button still says "SELECT COLOR." On a $1,649.99 PDP, that makes the button feel disabled or incomplete instead of confirming the next buying action.
RECOMMENDATION: Once a color is selected, change the button to "Add to Cart - $1,649.99" or "Add Polished Tips to Cart." If a required option is missing, show the missing option directly above the button instead of leaving the CTA ambiguous.
REFERENCE: cta-design-and-placement.md:Finding 14
PRIORITY: HIGH
**Why this matters:** Specific CTA labels reduce uncertainty because shoppers scan buttons out of context; generic or misleading labels cause users to hesitate before committing.
↳ cta-design-and-placement.md, Finding 14 (Nielsen Norman Group) [Gold]
```

```
FINDING: PARTIAL
TITLE: Primary CTA Contrast Is Weaker Than the Header Search and Navigation
SECTION: cta-contrast
ELEMENT: #ProductSubmitButton-template--20109859586113__main
SOURCE: VISUAL
OBSERVATION: The CTA uses a pale peach fill with white text, while the header search, vehicle selector, and black navigation area carry stronger contrast. The purchase action does not visually dominate the product module.
RECOMMENDATION: Use the brand blue or a high-contrast orange with dark text, keep the button filled, and reserve this treatment only for the primary purchase action. The button should be the strongest color block in the right column.
REFERENCE: cta-design-and-placement.md:Finding 2
PRIORITY: MEDIUM
**Why this matters:** CTA color is not about a universal best color; the button must contrast with its local surroundings enough to win attention.
↳ cta-design-and-placement.md, Finding 2 (CXL) [Silver]
```

### trust-credibility cluster

```
FINDING: FAIL
TITLE: No Reviews or Star Rating Near a $1,649 Product Decision
SECTION: reviews-display
ELEMENT: #ProductInfo-template--20109859586113__main (title/price area)
SOURCE: BOTH
OBSERVATION: The visible product module shows title, color, price, BNPL, quantity, and CTA, but no star rating, review count, verified-buyer language, or review anchor. This leaves a high-ticket automotive purchase without social proof at the moment of evaluation.
RECOMMENDATION: Add a review row directly under the title: star rating, review count, and a "Read reviews" anchor. If this specific SKU has few reviews, show verified brand/category reviews nearby and mark the product-specific count honestly.
REFERENCE: trust-and-credibility.md:Finding 4
PRIORITY: HIGH
**Why this matters:** Reviews matter more for expensive products because higher perceived risk increases reliance on social proof.
↳ trust-and-credibility.md, Finding 4 (Spiegel Research Center, Northwestern University, 2017) [Gold]
```

```
FINDING: PARTIAL
TITLE: Fitment and Return Confidence Are Below the Purchase Zone
SECTION: trust-above-fold
ELEMENT: #ProductInfo-template--20109859586113__main
SOURCE: VISUAL
OBSERVATION: The page has a "Select your vehicle" utility in the header and specifications lower on the page, but the purchase zone does not state "Fits 2016-2018 Focus RS," return terms, warranty, install support, or what is included. Buyers have to infer confidence from scattered content.
RECOMMENDATION: Add a compact trust strip below the CTA: "Fits 2016-2018 Focus RS," "Hardware included," "Secure checkout," "Returns/warranty details," and "Free shipping eligibility." Link each item to the relevant details section.
REFERENCE: trust-and-credibility.md:Finding 15
PRIORITY: MEDIUM
**Why this matters:** Guarantees and confidence cues work best when framed as positive promises near the decision point, not buried after the shopper has already hesitated.
↳ trust-and-credibility.md, Finding 15 (Conversion Rate Experts) [Bronze]
```

### pricing cluster

```
FINDING: PARTIAL
TITLE: Compare-At Price Does Not Explain the Savings
SECTION: price-anchoring
ELEMENT: div.price.h3-size
SOURCE: BOTH
OBSERVATION: The page shows $1,649.99 next to a struck $1,847.99 price, but it does not state the dollar savings, percent savings, or whether the crossed-out value is MSRP, previous AWDMods price, or manufacturer list price.
RECOMMENDATION: Add a clear savings label such as "Save $198 (11%) vs. MSRP" only if the anchor is accurate. If the anchor is not MSRP, label it honestly as "Was" or remove it.
REFERENCE: pricing-psychology.md:Finding 1
PRIORITY: MEDIUM
**Why this matters:** Anchors shape price judgments, but unexplained anchors can look arbitrary on high-ticket products.
↳ pricing-psychology.md, Finding 1 (Tversky & Kahneman; Ariely et al.) [Gold]
```

```
FINDING: PARTIAL
TITLE: Free Shipping Claim Is Not Confirmed at Product Level
SECTION: shipping-cost-display
ELEMENT: promo bar + #ProductInfo-template--20109859586113__main
SOURCE: VISUAL
OBSERVATION: The top promo says "FREE SHIPPING on most orders $75+ -- Contiguous US only," but the product module never confirms whether this heavy exhaust qualifies, what shipping method applies, or whether oversized freight exceptions exist.
RECOMMENDATION: Under the price or CTA, add a product-specific line: "Qualifies for free contiguous-US shipping" or "Shipping calculated because oversized." Do not rely only on the global promo bar for an expensive, physically large part.
REFERENCE: free-shipping.md:Finding 2
PRIORITY: HIGH
**Why this matters:** Unexpected shipping costs are a top controllable abandonment reason; product-level clarity prevents late-stage cost surprise.
↳ free-shipping.md, Finding 2 (Baymard Institute) [Gold]
```

### content-seo cluster

```
FINDING: FAIL
TITLE: Product Name Is Rendered as H2 Instead of the Main H1
SECTION: value-proposition
ELEMENT: div.product__title h2.b-main-title.h3
SOURCE: CODE
OBSERVATION: The captured DOM contains no H1. The visible product title is an H2, so the page is missing a clear main heading for accessibility, page structure, and search-result interpretation.
RECOMMENDATION: Render the product title as the page's single H1. Keep visual styling identical if needed, but correct the semantic element.
REFERENCE: title-formulas-serp-psychology.md
PRIORITY: HIGH
**Why this matters:** A PDP needs one clear primary heading that identifies the product for users, assistive technology, and search engines.
```

```
FINDING: FAIL
TITLE: Description Copy Contains Typos and Weak Benefit Framing
SECTION: value-proposition
ELEMENT: div.content-truncator__content.product__description
SOURCE: BOTH
OBSERVATION: The description includes visible copy errors: "so would this would" and "thst." It also repeats product-name phrasing before explaining the buyer outcome. For a premium exhaust, the copy should make the sound, fitment, material, and included hardware feel confidence-building.
RECOMMENDATION: Rewrite the opening paragraph around outcomes first: aggressive Borla ATAK sound, direct bolt-on fitment for 2016-2018 Focus RS, stainless construction, included hardware/instructions, and tip-finish choice. Then list specs below.
REFERENCE: benefit-first-descriptions.md:Finding 1
PRIORITY: HIGH
**Why this matters:** Buyers evaluate outcomes before specifications; typo-heavy copy makes a premium part feel less credible.
↳ benefit-first-descriptions.md, Finding 1 (Levitt; Christensen) [Silver]
```

```
FINDING: PARTIAL
TITLE: Product Metadata Omits Reviews, Return Policy, and Shipping Details
SECTION: value-proposition
ELEMENT: script[type="application/ld+json"]
SOURCE: CODE
OBSERVATION: The page has Product JSON-LD with name, image, description, SKU, brand, and offers. It does not include aggregateRating/review data, shippingDetails, or MerchantReturnPolicy fields.
RECOMMENDATION: Extend the product metadata for Google's merchant listing path with accurate aggregateRating/review data when available, shippingDetails, and return policy data. Keep values synchronized with the Shopify product/feed source.
REFERENCE: schema-product-markup.md:Finding 1
PRIORITY: MEDIUM
**Why this matters:** Ecommerce PDPs are merchant listing pages; richer product metadata supports enhanced search listings and AI-shopping comparison surfaces.
↳ schema-product-markup.md, Finding 1 (Google Search Central) [Gold]
```
