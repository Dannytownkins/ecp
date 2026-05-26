"""acquire.md Step 1d — configurator / fitment dual-state capture (Cursor URL bootstrap).

When at least two required ``<select>`` elements exist and the primary CTA is disabled,
selects the first valid option in each, waits for dynamic updates, and captures one
``{prefix}configured.jpg`` for the baton ``configured_state`` field.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

_DETECT_JS = r"""(function(){
  var selects = Array.from(document.querySelectorAll("select"));
  var required = selects.filter(function(s){
    return s.required || s.getAttribute("aria-required") === "true";
  });
  var btns = Array.from(document.querySelectorAll(
    'button[type="submit"],[class*="add-to-cart"],[name="add"],[aria-label*="Add to"],[aria-label*="add to"]'
  ));
  var cta = null;
  for (var b=0;b<btns.length;b++) {
    var r = btns[b].getBoundingClientRect();
    if (r.width>0 && r.height>0) { cta = btns[b]; break; }
  }
  if (!cta && btns[0]) cta = btns[0];
  return {
    requiredCount: required.length,
    ctaDisabled: cta ? !!cta.disabled : false,
    match: required.length >= 2 && cta && cta.disabled
  };
})()"""

_APPLY_JS = r"""(function(){
  var selects = Array.from(document.querySelectorAll("select")).filter(function(s){
    return s.required || s.getAttribute("aria-required") === "true";
  });
  for (var i=0;i<selects.length;i++) {
    var s = selects[i];
    var j = 0;
    for (var k=0;k<s.options.length;k++) {
      if (s.options[k].value && !s.options[k].disabled) { j = k; break; }
    }
    if (s.options.length > j) s.selectedIndex = j;
    else if (s.options.length) s.selectedIndex = 0;
    s.dispatchEvent(new Event("input", {bubbles: true}));
    s.dispatchEvent(new Event("change", {bubbles: true}));
  }
  return {ok: true, n: selects.length};
})()"""

_CTA_PRICE_JS = r"""(function(){
  var btns = Array.from(document.querySelectorAll(
    'button[type="submit"],[class*="add-to-cart"],[name="add"],[aria-label*="Add"]'
  ));
  var cta = btns[0] || null;
  var price = "";
  var el = document.querySelector("[class*='price'],[itemprop='price'],[data-product-price]");
  if (el) price = (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 120);
  return {
    ctaText: cta ? (cta.textContent || "").trim().replace(/\s+/g, " ").slice(0, 120) : "",
    ctaEnabled: cta ? !cta.disabled : null,
    price: price
  };
})()"""


def try_configured_state_capture(
    *,
    ev: Callable[[str], Any],
    scroll_to_y: Callable[[int], int],
    eng_dir: Path,
    shot_jpeg: Callable[[Path, int], tuple[Path, str, str | None, str]],
    file_prefix: str,
) -> dict[str, Any] | None:
    """Return ``configured_state`` dict for the baton or ``None`` if not applicable.

    Assumes default-state DOM is already saved; this mutates the live page.
    """
    scroll_to_y(0)
    time.sleep(0.4)
    det = ev("JSON.stringify(" + _DETECT_JS + ")")
    dct = _parse_obj(det) if not isinstance(det, dict) else det
    if not dct or not dct.get("match"):
        return None
    try:
        ev("JSON.stringify(" + _APPLY_JS + ")")
    except (OSError, RuntimeError, TypeError, ValueError):
        return None
    time.sleep(1.5)
    try:
        cta_raw = ev("JSON.stringify(" + _CTA_PRICE_JS + ")")
        cta_info: Any = _parse_obj(cta_raw) if not isinstance(cta_raw, dict) else cta_raw
    except (OSError, RuntimeError, TypeError, ValueError):
        cta_info = {}
    rel = f"{file_prefix}configured.jpg" if file_prefix else "configured.jpg"
    out = eng_dir / rel
    try:
        path, _h, _f, _e = shot_jpeg(out, 80)
    except (OSError, RuntimeError) as exc:
        print(f"STATUS: PARTIAL - configurator screenshot failed: {exc}", flush=True)
        return None
    if not path.exists() or path.stat().st_size < 100:
        return None
    return {
        "screenshot": rel,
        "cta_text": str((cta_info or {}).get("ctaText") or ""),
        "cta_enabled": (cta_info or {}).get("ctaEnabled") if cta_info else None,
        "price": str((cta_info or {}).get("price") or ""),
    }


def _parse_obj(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            o = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(o, str):
            try:
                return json.loads(o)
            except json.JSONDecodeError:
                return {}
        if isinstance(o, dict):
            return o
    return {}
