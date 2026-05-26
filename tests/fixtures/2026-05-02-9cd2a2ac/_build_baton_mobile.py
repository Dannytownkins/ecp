"""Build baton-mobile.json + dom-mobile.html for awdmods homepage acquisition."""
import json, re, os, tempfile, datetime

DIR = r"C:\Users\Daniel Kinsner\OneDrive\Documents\GitHub\ecommerce-conversion-psychology\docs\ecp\2026-05-02-9cd2a2ac"

# --- Load raw DOM (returned by agent-browser eval as JSON-encoded string) ---
with open(os.path.join(DIR, "dom-mobile-raw.html"), "r", encoding="utf-8") as f:
    raw = f.read().strip()
# eval output is wrapped as JSON string
try:
    dom = json.loads(raw)
except Exception:
    dom = raw

# --- Preprocess DOM ---
# Strip scripts/styles
dom = re.sub(r"<script\b[^>]*>.*?</script>", "", dom, flags=re.DOTALL | re.IGNORECASE)
dom = re.sub(r"<style\b[^>]*>.*?</style>", "", dom, flags=re.DOTALL | re.IGNORECASE)
# Strip data-* attrs
dom = re.sub(r'\sdata-[\w-]+="[^"]*"', "", dom)
dom = re.sub(r"\sdata-[\w-]+='[^']*'", "", dom)
# Strip svg internal shapes
dom = re.sub(r"<(path|polygon|circle|rect|line|polyline|ellipse)\b[^>]*/?>", "", dom, flags=re.IGNORECASE)
dom = re.sub(r"</(path|polygon|circle|rect|line|polyline|ellipse)>", "", dom, flags=re.IGNORECASE)
# Strip HTML comments
dom = re.sub(r"<!--.*?-->", "", dom, flags=re.DOTALL)
# Collapse whitespace
dom = re.sub(r"\n\s*\n", "\n", dom)

dom_size = len(dom.encode("utf-8"))
dom_mode = "full" if dom_size < 300_000 else ("reduced" if dom_size < 500_000 else "skeleton")

with open(os.path.join(DIR, "dom-mobile.html"), "w", encoding="utf-8") as f:
    f.write(dom)

# --- Load page_head ---
with open(os.path.join(DIR, "page-head-mobile.json"), "r", encoding="utf-8") as f:
    ph_raw = f.read().strip()
try:
    page_head = json.loads(json.loads(ph_raw))
except Exception:
    page_head = json.loads(ph_raw)

# --- Load element captures from each section ---
def load_elems(name):
    p = os.path.join(DIR, name)
    with open(p, "r", encoding="utf-8") as f:
        s = f.read().strip()
    try:
        v = json.loads(json.loads(s))
    except Exception:
        v = json.loads(s)
    return v if isinstance(v, list) else []

s1 = load_elems("elements-mobile-s1.json")
s2 = load_elems("elements-mobile-s2.json")
s3 = load_elems("elements-mobile-s3.json")

# Dedup by (tag, x, y), keep largest area
all_elems = []
seen = {}
for batch in (s1, s2, s3):
    for el in batch:
        key = (el["tag"], el["x"], el["y"])
        area = el["width"] * el["height"]
        if key in seen:
            existing = seen[key]
            if area > existing["width"] * existing["height"]:
                idx = all_elems.index(existing)
                all_elems[idx] = el
                seen[key] = el
        else:
            seen[key] = el
            all_elems.append(el)

# Cap to 200
all_elems = all_elems[:200]

# Assign e_index, build rect, drop flat fields
elements = []
for i, el in enumerate(all_elems):
    rect = {"x": el["x"], "y": el["y"], "width": el["width"], "height": el["height"]}
    new = {
        "e_index": f"e{i}",
        "tag": el["tag"],
        "selector": el.get("selector", el["tag"]),
        "rect": rect,
        "scroll_y_at_capture": el.get("scroll_y_at_capture", 0),
        "role": el.get("role", el["tag"]),
        "accessible_name": el.get("accessible_name", "")[:120],
        "text_content": el.get("text_content", "")[:240],
        "is_above_fold": bool(el.get("is_above_fold", False)),
        "is_sticky": bool(el.get("is_sticky", False)),
        "is_offscreen": bool(el.get("is_offscreen", False)),
    }
    elements.append(new)

# --- Sections ---
PAGE_HEIGHT = 2305
sections = [
    {
        "label": "Hero banner and primary navigation",
        "slug": "hero",
        "clusters": ["visual-cta", "category-navigation", "product-media", "performance-ux"],
        "scroll_y_top": 0,
        "scroll_y_bottom": 699,
        "screenshot_ref": "section-1-mobile.jpg",
        "occluded": False
    },
    {
        "label": "Featured collections and product grid",
        "slug": "collections",
        "clusters": ["product-media", "category-navigation", "pricing", "trust-credibility"],
        "scroll_y_top": 700,
        "scroll_y_bottom": 1449,
        "screenshot_ref": "section-2-mobile.jpg",
        "occluded": False
    },
    {
        "label": "Brand content and footer",
        "slug": "footer",
        "clusters": ["content-seo", "trust-credibility", "checkout-flows", "category-navigation"],
        "scroll_y_top": 1450,
        "scroll_y_bottom": PAGE_HEIGHT,
        "screenshot_ref": "section-3-mobile.jpg",
        "occluded": False
    },
]

# --- Load meta.json ---
with open(os.path.join(DIR, "meta.json"), "r", encoding="utf-8") as f:
    meta = json.load(f)

baton = {
    "schema_version": 1,
    "engagement_id": meta.get("id", "2026-05-02-9cd2a2ac"),
    "device": "mobile",
    "url": "https://www.awdmods.com/",
    "captured_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    "source_mode": "url-dual",
    "status": "COMPLETE",
    "viewport": {
        "width": 390,
        "height": 844,
        "dpr": 3,
        "dpr_requested": 3,
        "dpr_actual": 3
    },
    "capture_state": {
        "hydration": "post-hydration",
        "overlays_detected": [],
        "page_height_px": PAGE_HEIGHT
    },
    "elements": elements,
    "sections": sections,
    "page_head": page_head,
    "telemetry": {
        "playwright_version": "agent-browser 0.21.4",
        "chromium_binary": "chromium",
        "dom_size_bytes": dom_size,
        "dom_mode": dom_mode
    }
}

# Atomic write
out = os.path.join(DIR, "baton-mobile.json")
fd, tmp = tempfile.mkstemp(suffix=".tmp", dir=DIR)
try:
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        json.dump(baton, f, sort_keys=True, ensure_ascii=False, indent=2)
    os.replace(tmp, out)
except Exception:
    if os.path.exists(tmp):
        os.unlink(tmp)
    raise

print(f"WROTE baton-mobile.json — elements={len(elements)} sections={len(sections)} dom_bytes={dom_size} dom_mode={dom_mode}")
