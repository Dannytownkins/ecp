import json, os, re, datetime, tempfile

ENG_DIR = r"C:\Users\Daniel Kinsner\OneDrive\Documents\GitHub\ecommerce-conversion-psychology\docs\ecp\2026-05-02-9cd2a2ac"

# --- Load raw DOM (it's wrapped as a JSON string by agent-browser eval output) ---
with open(os.path.join(ENG_DIR, "dom-raw.html"), "r", encoding="utf-8", errors="replace") as f:
    raw = f.read().strip()
# strip surrounding quotes if json-string
if raw.startswith('"') and raw.endswith('"'):
    try:
        raw = json.loads(raw)
    except Exception:
        pass

html = raw
# preprocess
html = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
html = re.sub(r"<style[\s\S]*?</style>", "", html, flags=re.IGNORECASE)
html = re.sub(r"\sdata-[a-zA-Z0-9_\-]+=\"[^\"]*\"", "", html)
html = re.sub(r"\sdata-[a-zA-Z0-9_\-]+='[^']*'", "", html)
# strip svg children
html = re.sub(r"<svg([^>]*)>[\s\S]*?</svg>", lambda m: f"<svg{m.group(1)}/>", html, flags=re.IGNORECASE)
# strip comments
html = re.sub(r"<!--[\s\S]*?-->", "", html)

with open(os.path.join(ENG_DIR, "dom.html"), "w", encoding="utf-8", newline="\n") as f:
    f.write(html)
dom_size = len(html.encode("utf-8"))
print(f"DOM size: {dom_size} bytes")

# --- Load element captures ---
def load_eval_json(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        s = fh.read().strip()
    # strip ANSI
    s = re.sub(r"\x1b\[[0-9;]*m", "", s)
    if s.startswith('"'):
        s = json.loads(s)
    return json.loads(s)

s1 = load_eval_json(os.path.join(ENG_DIR, "elements-s1.json"))
s2 = load_eval_json(os.path.join(ENG_DIR, "elements-s2.json"))
s3 = load_eval_json(os.path.join(ENG_DIR, "elements-s3.json"))

all_raw = s1 + s2 + s3
seen = {}
ordered = []
for el in all_raw:
    key = (el.get("tag"), el.get("x"), el.get("y"))
    if key in seen:
        existing = seen[key]
        if el.get("width",0)*el.get("height",0) > existing.get("width",0)*existing.get("height",0):
            ordered.remove(existing)
            ordered.append(el)
            seen[key] = el
        continue
    seen[key] = el
    ordered.append(el)

# cap at 200
ordered = ordered[:200]
elements = []
for i, el in enumerate(ordered):
    el2 = {
        "e_index": f"e{i}",
        "tag": el.get("tag"),
        "selector": el.get("selector"),
        "rect": {"x": el.get("x",0), "y": el.get("y",0), "width": el.get("width",0), "height": el.get("height",0)},
        "scroll_y_at_capture": el.get("scroll_y_at_capture",0),
        "role": el.get("role",""),
        "accessible_name": el.get("accessible_name","") or "",
        "text_content": el.get("text_content","") or "",
        "is_above_fold": bool(el.get("is_above_fold")),
        "is_sticky": bool(el.get("is_sticky")),
        "is_offscreen": bool(el.get("is_offscreen")),
    }
    elements.append(el2)
print(f"Elements: {len(elements)}")

# page_head
ph_raw = open(os.path.join(ENG_DIR, "page-head.json"), "r", encoding="utf-8", errors="replace").read().strip()
ph_raw = re.sub(r"\x1b\[[0-9;]*m", "", ph_raw)
if ph_raw.startswith('"'):
    ph_raw = json.loads(ph_raw)
page_head = json.loads(ph_raw)

# meta.json for engagement_id
with open(os.path.join(ENG_DIR, "meta.json"), "r", encoding="utf-8") as f:
    meta = json.load(f)
engagement_id = meta.get("id", "2026-05-02-9cd2a2ac")

PAGE_HEIGHT = 2942

sections = [
    {
        "label": "Hero, header navigation and primary CTA",
        "slug": "hero",
        "clusters": ["visual-cta", "category-navigation", "trust-credibility", "content-seo"],
        "scroll_y_top": 0,
        "scroll_y_bottom": 979,
        "screenshot_ref": "section-1.jpg"
    },
    {
        "label": "Featured products and category content",
        "slug": "featured",
        "clusters": ["visual-cta", "pricing", "product-media", "category-navigation", "trust-credibility"],
        "scroll_y_top": 980,
        "scroll_y_bottom": 1814,
        "screenshot_ref": "section-2.jpg"
    },
    {
        "label": "Footer, newsletter and payment information",
        "slug": "footer",
        "clusters": ["trust-credibility", "checkout-flows", "content-seo", "category-navigation"],
        "scroll_y_top": 1815,
        "scroll_y_bottom": 2942,
        "screenshot_ref": "section-3.jpg"
    }
]

baton = {
    "schema_version": 1,
    "engagement_id": engagement_id,
    "device": "desktop",
    "url": "https://www.awdmods.com/",
    "captured_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    "viewport": {"width": 1920, "height": 1080, "dpr_requested": 1, "dpr_actual": 1},
    "capture_state": {
        "hydration": "post-hydration",
        "overlays_detected": [],
        "page_height_px": PAGE_HEIGHT
    },
    "elements": elements,
    "sections": sections,
    "page_head": page_head,
    "telemetry": {
        "playwright_version": "agent-browser-0.21.4",
        "chromium_binary": "chromium-default",
        "dom_size_bytes": dom_size
    },
    "status": "COMPLETE",
    "source_mode": "url-dual"
}

# atomic write
out = os.path.join(ENG_DIR, "baton.json")
fd, tmp = tempfile.mkstemp(suffix=".tmp", dir=ENG_DIR)
with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
    json.dump(baton, f, ensure_ascii=False, indent=2)
os.replace(tmp, out)
print(f"baton.json written: {os.path.getsize(out)} bytes")
