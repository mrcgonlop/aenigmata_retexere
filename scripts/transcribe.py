"""Manual transcription interface for manuscript folios.

Starts a local web server and opens the browser with:
  - Zoomable manuscript image (scroll-wheel)
  - Greek textarea with dead-key diacritic composition
  - Virtual keyboard for all characters + accents
  - Folio navigation (prev / next / jump by number)
  - Auto-save on every keystroke (debounced 1 s) to:
      data/manuscripts/{id}/transcriptions/{folio}_manual.json

Usage:
    python scripts/transcribe.py --manuscript vat.gr.1209 --folio 41
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_ROOT        = Path(__file__).parent.parent
_MANUSCRIPTS = _ROOT / "data" / "manuscripts"
_DEFAULT_PORT = 8765

# ---------------------------------------------------------------------------
# Character maps
# ---------------------------------------------------------------------------

# Physical key → Greek letter (intercepted by the textarea keydown handler)
_KEY_MAP: dict[str, str] = {
    "Q": "Θ", "W": "Ω", "E": "Ε", "R": "Ρ", "T": "Τ",
    "Y": "Υ", "U": "Ϲ", "I": "Ι", "O": "Ο", "P": "Π",
    "A": "Α", "S": "Σ", "D": "Δ", "F": "Φ", "G": "Γ",
    "H": "Η", "J": "Ξ", "K": "Κ", "L": "Λ",
    "Z": "Ζ", "X": "Χ", "C": "Ψ", "V": "Β", "N": "Ν", "M": "Μ",
    ";": "·",   # ano teleia (high dot)
    ":": "÷",   # dicolon
}

# Dead-key definitions: physical key → modifier name
# Modifier name is used as the compose-table key component.
_DEAD_KEYS: dict[str, str] = {
    "[":  "smooth",   # ψιλή  — smooth breathing
    "]":  "rough",    # δασεῖα — rough breathing
    "'":  "acute",    # ὀξεῖα  — acute accent
    "`":  "grave",    # βαρεῖα  — grave accent
    "=":  "circ",     # περισπωμένη — circumflex
    "\\":  "sub",     # ὑπογεγραμμένη — iota subscript
    "|":  "diaer",    # διαίρεσις — dieresis
}

# Display label for each dead key (shown on the virtual keyboard button)
_DEAD_LABELS: dict[str, tuple[str, str]] = {
    # modifier → (glyph, key_hint)
    "smooth": ("᾿",  "["),
    "rough":  ("῾",  "]"),
    "acute":  ("΄",  "'"),
    "grave":  ("`",  "`"),
    "circ":   ("͂",  "="),
    "sub":    ("ͅ",  "\\"),
    "diaer":  ("¨",  "|"),
}

# Uppercase → lowercase mapping for key label display
_LOWER: dict[str, str] = {
    "Α":"α","Β":"β","Γ":"γ","Δ":"δ","Ε":"ε","Ζ":"ζ","Η":"η","Θ":"θ",
    "Ι":"ι","Κ":"κ","Λ":"λ","Μ":"μ","Ν":"ν","Ξ":"ξ","Ο":"ο","Π":"π",
    "Ρ":"ρ","Σ":"σ","Τ":"τ","Υ":"υ","Φ":"φ","Χ":"χ","Ψ":"ψ","Ω":"ω",
    "Ϲ":"ϲ",
}

# Compose table: "sorted_mods|UPPERCASE_KEY" → precomposed Unicode character.
# Modifier names are sorted alphabetically before joining with "+".
_COMPOSE: dict[str, str] = {
    # ── Smooth breathing only ──────────────────────────────────────
    "smooth|A": "ἀ", "smooth|E": "ἐ", "smooth|H": "ἠ",
    "smooth|I": "ἰ", "smooth|O": "ὀ", "smooth|Y": "ὐ", "smooth|W": "ὠ",
    # ── Rough breathing only ───────────────────────────────────────
    "rough|A": "ἁ",  "rough|E": "ἑ",  "rough|H": "ἡ",
    "rough|I": "ἱ",  "rough|O": "ὁ",  "rough|Y": "ὑ",  "rough|W": "ὡ",
    "rough|R": "ῥ",
    # ── Acute only ────────────────────────────────────────────────
    "acute|A": "ά",  "acute|E": "έ",  "acute|H": "ή",
    "acute|I": "ί",  "acute|O": "ό",  "acute|Y": "ύ",  "acute|W": "ώ",
    # ── Grave only ────────────────────────────────────────────────
    "grave|A": "ὰ",  "grave|E": "ὲ",  "grave|H": "ὴ",
    "grave|I": "ὶ",  "grave|O": "ὸ",  "grave|Y": "ὺ",  "grave|W": "ὼ",
    # ── Circumflex only ───────────────────────────────────────────
    "circ|A": "ᾶ",  "circ|H": "ῆ",  "circ|I": "ῖ",  "circ|Y": "ῦ",  "circ|W": "ῶ",
    # ── Smooth + acute ────────────────────────────────────────────
    "acute+smooth|A": "ἄ", "acute+smooth|E": "ἔ", "acute+smooth|H": "ἤ",
    "acute+smooth|I": "ἴ", "acute+smooth|O": "ὄ", "acute+smooth|Y": "ὔ", "acute+smooth|W": "ὤ",
    # ── Rough + acute ─────────────────────────────────────────────
    "acute+rough|A": "ἅ",  "acute+rough|E": "ἕ",  "acute+rough|H": "ἥ",
    "acute+rough|I": "ἵ",  "acute+rough|O": "ὅ",  "acute+rough|Y": "ὕ",  "acute+rough|W": "ὥ",
    # ── Smooth + grave ────────────────────────────────────────────
    "grave+smooth|A": "ἂ", "grave+smooth|E": "ἒ", "grave+smooth|H": "ἢ",
    "grave+smooth|I": "ἲ", "grave+smooth|O": "ὂ", "grave+smooth|Y": "ὒ", "grave+smooth|W": "ὢ",
    # ── Rough + grave ─────────────────────────────────────────────
    "grave+rough|A": "ἃ",  "grave+rough|E": "ἓ",  "grave+rough|H": "ἣ",
    "grave+rough|I": "ἳ",  "grave+rough|O": "ὃ",  "grave+rough|Y": "ὓ",  "grave+rough|W": "ὣ",
    # ── Smooth + circumflex ───────────────────────────────────────
    "circ+smooth|A": "ἆ", "circ+smooth|H": "ἦ", "circ+smooth|I": "ἶ",
    "circ+smooth|Y": "ὖ", "circ+smooth|W": "ὦ",
    # ── Rough + circumflex ────────────────────────────────────────
    "circ+rough|A": "ἇ",  "circ+rough|H": "ἧ",  "circ+rough|I": "ἷ",
    "circ+rough|Y": "ὗ",  "circ+rough|W": "ὧ",
    # ── Iota subscript alone ──────────────────────────────────────
    "sub|A": "ᾳ",  "sub|H": "ῃ",  "sub|W": "ῳ",
    # ── Subscript + smooth ────────────────────────────────────────
    "smooth+sub|A": "ᾀ", "smooth+sub|H": "ᾐ", "smooth+sub|W": "ᾠ",
    # ── Subscript + rough ─────────────────────────────────────────
    "rough+sub|A": "ᾁ",  "rough+sub|H": "ᾑ",  "rough+sub|W": "ᾡ",
    # ── Sub + smooth + acute ──────────────────────────────────────
    "acute+smooth+sub|A": "ᾄ", "acute+smooth+sub|H": "ᾔ", "acute+smooth+sub|W": "ᾤ",
    # ── Sub + rough + acute ───────────────────────────────────────
    "acute+rough+sub|A": "ᾅ",  "acute+rough+sub|H": "ᾕ",  "acute+rough+sub|W": "ᾥ",
    # ── Sub + smooth + grave ──────────────────────────────────────
    "grave+smooth+sub|A": "ᾂ", "grave+smooth+sub|H": "ᾒ", "grave+smooth+sub|W": "ᾢ",
    # ── Sub + rough + grave ───────────────────────────────────────
    "grave+rough+sub|A": "ᾃ",  "grave+rough+sub|H": "ᾓ",  "grave+rough+sub|W": "ᾣ",
    # ── Sub + smooth + circ ───────────────────────────────────────
    "circ+smooth+sub|A": "ᾆ", "circ+smooth+sub|H": "ᾖ", "circ+smooth+sub|W": "ᾦ",
    # ── Sub + rough + circ ────────────────────────────────────────
    "circ+rough+sub|A": "ᾇ",  "circ+rough+sub|H": "ᾗ",  "circ+rough+sub|W": "ᾧ",
    # ── Sub + acute ───────────────────────────────────────────────
    "acute+sub|A": "ᾴ", "acute+sub|H": "ῄ", "acute+sub|W": "ῴ",
    # ── Sub + grave ───────────────────────────────────────────────
    "grave+sub|A": "ᾲ", "grave+sub|H": "ῂ", "grave+sub|W": "ῲ",
    # ── Sub + circ ────────────────────────────────────────────────
    "circ+sub|A": "ᾷ",  "circ+sub|H": "ῇ",  "circ+sub|W": "ῷ",
    # ── Dieresis ──────────────────────────────────────────────────
    "diaer|I": "ϊ",        "diaer|Y": "ϋ",
    "acute+diaer|I": "ΐ",  "acute+diaer|Y": "ΰ",
    "grave+diaer|I": "ῒ",  "grave+diaer|Y": "ῢ",
    "circ+diaer|I":  "ῗ",  "circ+diaer|Y":  "ῧ",
}

# Virtual keyboard layout: rows of (trigger_key, greek_char) pairs
_KB_ROWS: list[list[tuple[str, str]]] = [
    [("Q","Θ"),("W","Ω"),("E","Ε"),("R","Ρ"),("T","Τ"),
     ("Y","Υ"),("U","Ϲ"),("I","Ι"),("O","Ο"),("P","Π")],
    [("A","Α"),("S","Σ"),("D","Δ"),("F","Φ"),("G","Γ"),
     ("H","Η"),("J","Ξ"),("K","Κ"),("L","Λ")],
    [("Z","Ζ"),("X","Χ"),("C","Ψ"),("V","Β"),("N","Ν"),("M","Μ")],
]

# Nomina sacra: (display_label, text_to_insert)
_NOMINA_SACRA: list[tuple[str, str]] = [
    ("ΙΣ̄",  "ΙΣ\u0305"),
    ("ΧΣ̄",  "ΧΣ\u0305"),
    ("ΘΣ̄",  "ΘΣ\u0305"),
    ("ΚΣ̄",  "ΚΣ\u0305"),
    ("ΠΝᾹ", "ΠΝΑ\u0305"),
    ("ΥΣ̄",  "ΥΣ\u0305"),
    ("ΠΗΡ̄", "ΠΗΡ\u0305"),
]

# ---------------------------------------------------------------------------
# HTML generator
# ---------------------------------------------------------------------------

def _list_folios(manuscript_dir: Path) -> list[str]:
    images_dir = manuscript_dir / "images"
    if not images_dir.exists():
        return []
    import re as _re
    def _folio_key(stem: str):
        # Sort numerically on leading digits, then lexically on any suffix (e.g. "123r", "123v")
        m = _re.match(r'^(\d+)(.*)', stem)
        return (int(m.group(1)), m.group(2)) if m else (float('inf'), stem)

    stems = sorted(
        (p.stem for p in images_dir.iterdir()
         if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}),
        key=_folio_key,
    )
    return stems


def _build_keyboard_html() -> str:
    rows = []
    # Dead-key row
    dead_keys_html = "".join(
        f'<button class="key key-dead" data-mod="{mod}" title="Press {hint} — {mod}">'
        f'<span class="gk">{glyph}</span><span class="kl">{hint}</span></button>'
        for mod, (glyph, hint) in _DEAD_LABELS.items()
    )
    rows.append(f'<div class="kb-row dead-row">{dead_keys_html}'
                f'<button class="key key-clear" id="btn-clear-mods" title="Clear modifiers">✕</button></div>')
    rows.append('<div id="compose-status"></div>')

    # Letter rows
    for row in _KB_ROWS:
        keys = "".join(
            f'<button class="key" data-char="{greek}" title="Press {k}">'
            f'<span class="gk">{greek}</span>'
            f'<span class="gk-lo">{_LOWER.get(greek, "")}</span>'
            f'<span class="kl">{k}</span></button>'
            for k, greek in row
        )
        rows.append(f'<div class="kb-row">{keys}</div>')

    # Nomina sacra row
    ns = "".join(
        f'<button class="key key-ns" data-char="{chars}" title="Nomen sacrum">'
        f'<span class="gk">{label}</span></button>'
        for label, chars in _NOMINA_SACRA
    )
    rows.append(f'<div class="kb-row ns-row">{ns}</div>')

    # Controls row
    rows.append(
        '<div id="kb-controls">'
        '<button class="key key-spec" data-char=" "><span class="gk">spc</span></button>'
        '<button class="key key-spec" data-char="&#10;"><span class="gk">↵</span></button>'
        '<button class="key key-spec" id="btn-bksp"><span class="gk">⌫</span></button>'
        '<button class="key key-spec" data-char="·"><span class="gk">·</span><span class="kl">;</span></button>'
        '<button class="key key-spec" data-char="÷"><span class="gk">÷</span><span class="kl">:</span></button>'
        '<button class="key key-spec" data-char="¶"><span class="gk">¶</span></button>'
        '</div>'
    )
    return "\n".join(rows)


def generate_html(manuscript: str, folio: str, folios: list[str]) -> str:
    key_map_js   = json.dumps(_KEY_MAP)
    dead_keys_js = json.dumps(_DEAD_KEYS)
    compose_js   = json.dumps(_COMPOSE, ensure_ascii=False)
    folios_js    = json.dumps(folios)
    keyboard_html = _build_keyboard_html()
    cur_idx      = folios.index(folio) if folio in folios else -1
    total        = len(folios)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Transcribe — {manuscript} f.{folio}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,sans-serif;background:#0c111d;color:#e2e8f0;
     height:100vh;display:flex;flex-direction:column;overflow:hidden}}

/* ── Header ── */
#hdr{{padding:6px 12px;background:#111827;border-bottom:1px solid #1f2937;
      display:flex;align-items:center;gap:10px;flex-shrink:0;flex-wrap:wrap}}
#hdr h1{{font-size:13px;font-weight:600;color:#f1f5f9}}
.meta{{font-size:11px;color:#6b7280}}
#folio-nav{{display:flex;align-items:center;gap:4px}}
#folio-nav button{{padding:2px 8px;border-radius:4px;border:1px solid #374151;
                   background:#1f2937;color:#94a3b8;cursor:pointer;font-size:12px}}
#folio-nav button:hover:not(:disabled){{background:#374151;color:#e2e8f0}}
#folio-nav button:disabled{{opacity:.35;cursor:default}}
#folio-input{{width:52px;padding:2px 5px;border-radius:4px;border:1px solid #374151;
              background:#0a0f1c;color:#e2e8f0;font-size:12px;text-align:center}}
#save-status{{font-size:11px;padding:2px 8px;border-radius:10px;background:#1f2937;
              color:#6b7280;transition:all .3s;margin-left:auto}}
#save-status.saving{{background:#1e3a1e;color:#86efac}}
#save-status.saved{{background:#1a2e1a;color:#4ade80}}
#save-status.error{{background:#3a1a1a;color:#f87171}}
#btn-ocr{{padding:3px 9px;border-radius:4px;border:none;cursor:pointer;font-size:11px;
          font-weight:500;background:#1f2937;color:#94a3b8}}
#btn-ocr.active{{background:#374151;color:#e2e8f0}}

/* ── Main layout ── */
#main{{display:flex;flex:1;overflow:hidden}}
#img-col{{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}}

/* ── Image pane ── */
#img-col{{flex:1;display:flex;flex-direction:column;overflow:hidden}}
#img-toolbar{{display:flex;align-items:center;gap:8px;padding:4px 10px;
              background:#111827;border-bottom:1px solid #1f2937;flex-shrink:0}}
#img-toolbar label{{font-size:10px;color:#6b7280}}
#zoom-slider{{width:110px;accent-color:#3b82f6;cursor:pointer}}
#zoom-label{{font-size:10px;color:#94a3b8;width:36px}}
#img-toolbar button{{padding:2px 7px;border-radius:4px;border:1px solid #374151;
                     background:#1f2937;color:#94a3b8;cursor:pointer;font-size:11px}}
#img-toolbar button:hover{{background:#374151;color:#e2e8f0}}
#img-pane{{flex:1;overflow:auto;background:#020617}}
#img-pane img{{display:block}}

/* ── Right pane ── */
#right{{width:400px;flex-shrink:0;display:flex;flex-direction:column;
        border-left:1px solid #1f2937}}
#tx-label{{padding:4px 10px;font-size:10px;color:#6b7280;background:#111827;
           border-bottom:1px solid #1f2937;flex-shrink:0}}
#tx{{flex:1;background:#0a0f1c;color:#f1f5f9;
     font-family:"Noto Serif","Times New Roman",Georgia,serif;
     font-size:15px;line-height:1.8;padding:10px;border:none;outline:none;
     resize:none;letter-spacing:.03em}}
#tx::selection{{background:#1e3a5f}}

/* OCR reference */
#ocr-panel{{flex-shrink:0;border-top:1px solid #1f2937;max-height:160px;
            display:none;flex-direction:column}}
#ocr-panel.open{{display:flex}}
#ocr-label{{padding:4px 10px;font-size:10px;color:#6b7280;background:#111827;flex-shrink:0}}
#ocr-text{{overflow-y:auto;flex:1;padding:6px 10px;
           font-family:"Noto Serif","Times New Roman",Georgia,serif;
           font-size:12px;color:#6b7280;line-height:1.6;white-space:pre-wrap}}

/* ── Keyboard ── */
#keyboard{{flex-shrink:0;padding:6px 6px 8px;background:#111827;
           border-top:1px solid #1f2937;user-select:none}}
.kb-row{{display:flex;gap:3px;justify-content:center;margin-bottom:3px}}
.key{{display:flex;flex-direction:column;align-items:center;justify-content:center;
      width:34px;height:50px;border-radius:5px;border:1px solid #374151;
      background:#1f2937;cursor:pointer;padding:0;gap:0;
      transition:background .1s,border-color .1s}}
.key:hover{{background:#2d3748;border-color:#4b5563}}
.key:active,.key.pressed{{background:#374151}}
.key .gk{{font-family:"Noto Serif","Times New Roman",Georgia,serif;
           font-size:15px;color:#e2e8f0;line-height:1}}
.key .gk-lo{{font-family:"Noto Serif","Times New Roman",Georgia,serif;
              font-size:11px;color:#6b7280;line-height:1.2}}
.key .kl{{font-size:8px;color:#4b5563;font-weight:600;margin-top:1px}}
/* Dead keys */
.key-dead{{width:34px;background:#0f1a2e;border-color:#1e3a5f}}
.key-dead.active{{background:#1e3a5f;border-color:#3b82f6;box-shadow:0 0 0 1px #3b82f644}}
.key-dead .gk{{font-size:16px;color:#7dd3fc}}
.key-dead .kl{{color:#2d5a8e}}
.key-clear{{width:26px;height:40px;border-radius:5px;border:1px solid #374151;
            background:#0f1a2e;cursor:pointer;color:#475569;font-size:11px}}
.key-clear:hover{{background:#1f2937;color:#94a3b8}}
/* Compose status */
#compose-status{{font-size:10px;color:#3b82f6;text-align:center;
                 min-height:14px;margin-bottom:2px;letter-spacing:.03em}}
/* Nomina sacra */
.key-ns{{width:auto;min-width:38px;padding:0 5px;height:40px}}
.key-ns .gk{{font-size:12px}}
.ns-row{{gap:4px}}
/* Controls */
.key-spec{{width:auto;min-width:42px;padding:0 7px;background:#0f1a2e;border-color:#1e3a5f}}
.key-spec .gk{{font-size:12px;color:#7dd3fc}}
.key-spec .kl{{color:#2d5a8e}}
#kb-controls{{display:flex;gap:3px;justify-content:center;margin-top:2px}}
</style>
</head>
<body>
<div id="hdr">
  <h1>Transcription</h1>
  <div class="meta">{manuscript}</div>
  <div id="folio-nav">
    <button id="btn-prev" {"disabled" if cur_idx <= 0 else ""}>◀</button>
    <input id="folio-input" value="{folio}" title="Folio number — press Enter to jump">
    <button id="btn-go">Go</button>
    <button id="btn-next" {"disabled" if cur_idx >= total - 1 else ""}>▶</button>
    <span class="meta">&nbsp;f.{folio} · {cur_idx+1}/{total}</span>
  </div>
  <button id="btn-ocr">OCR ref</button>
  <span id="save-status">ready</span>
</div>
<div id="main">
  <div id="img-col">
    <div id="img-toolbar">
      <label>Zoom</label>
      <input type="range" id="zoom-slider" min="10" max="400" value="100" step="5">
      <span id="zoom-label">100%</span>
      <button id="btn-zoom-fit">Fit</button>
      <button id="btn-zoom-100">1:1</button>
    </div>
    <div id="img-pane">
      <img id="folio-img" src="/image?folio={folio}" alt="folio {folio}">
    </div>
  </div>
  <div id="right">
    <div id="tx-label">Transcription — type with keyboard · dead keys for diacritics · auto-saved</div>
    <textarea id="tx" spellcheck="false" autocomplete="off" autocorrect="off"
              placeholder="Type Greek here…&#10;&#10;Dead keys (press before a vowel):&#10;  [ smooth   ] rough&#10;  ' acute     ` grave&#10;  = circumflex \\ iota-sub&#10;  | dieresis"></textarea>
    <div id="ocr-panel">
      <div id="ocr-label">OCR reference (read-only)</div>
      <div id="ocr-text"></div>
    </div>
    <div id="keyboard">
{keyboard_html}
    </div>
  </div>
</div>
<script>
const MANUSCRIPT = {json.dumps(manuscript)};
const FOLIO      = {json.dumps(folio)};
const FOLIOS     = {folios_js};
const KEY_MAP    = {key_map_js};
const DEAD_KEYS  = {dead_keys_js};
const COMPOSE    = {compose_js};

// ── Combining-character fallback for unrecognised compose sequences ──
const COMBINING = {{
  smooth: '\u0313', rough: '\u0314', acute: '\u0301',
  grave:  '\u0300', circ:  '\u0342', sub:   '\u0345', diaer: '\u0308',
}};

// ── State ──
const ta        = document.getElementById('tx');
const statusEl  = document.getElementById('save-status');
let saveTimer   = null;
let deadMods    = new Set();

// ── Folio navigation ──
const curIdx = FOLIOS.indexOf(FOLIO);
function navigate(f) {{ window.location.href = '/?folio=' + encodeURIComponent(f); }}

document.getElementById('btn-prev').addEventListener('click', () => {{
  if (curIdx > 0) navigate(FOLIOS[curIdx - 1]);
}});
document.getElementById('btn-next').addEventListener('click', () => {{
  if (curIdx < FOLIOS.length - 1) navigate(FOLIOS[curIdx + 1]);
}});
document.getElementById('btn-go').addEventListener('click', () => {{
  const f = document.getElementById('folio-input').value.trim();
  if (FOLIOS.includes(f)) navigate(f);
  else document.getElementById('folio-input').style.borderColor = '#ef4444';
}});
document.getElementById('folio-input').addEventListener('keydown', e => {{
  document.getElementById('folio-input').style.borderColor = '';
  if (e.key === 'Enter') document.getElementById('btn-go').click();
  e.stopPropagation(); // don't let it reach Greek key handler
}});

// ── Load existing manual transcript ──
fetch('/manual?folio=' + encodeURIComponent(FOLIO))
  .then(r => r.json()).then(d => {{ if (d && d.text !== undefined) {{ ta.value = d.text; setStatus('saved'); }} }})
  .catch(() => {{}});

// ── Load OCR reference ──
fetch('/ocr?folio=' + encodeURIComponent(FOLIO))
  .then(r => r.json()).then(d => {{
    if (!d) return;
    const res = d.results && d.results[0];
    if (!res) return;
    const text = res.lines ? res.lines.map(l => l.text).join('\\n') : (res.text || '');
    document.getElementById('ocr-text').textContent = text;
  }}).catch(() => {{}});

document.getElementById('btn-ocr').addEventListener('click', function() {{
  document.getElementById('ocr-panel').classList.toggle('open');
  this.classList.toggle('active');
}});

// ── Save ──
function setStatus(s) {{
  statusEl.className = s;
  statusEl.textContent = {{saving:'saving…',saved:'saved ✓',error:'save failed',ready:'ready'}}[s] || s;
}}
function scheduleAutosave() {{
  setStatus('saving');
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {{
    fetch('/manual?folio=' + encodeURIComponent(FOLIO), {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{manuscript: MANUSCRIPT, folio: FOLIO, source: 'manual', text: ta.value}}),
    }}).then(() => setStatus('saved')).catch(() => setStatus('error'));
  }}, 1000);
}}
ta.addEventListener('input', scheduleAutosave);

// ── Dead key compose ──
function composeKey() {{ return [...deadMods].sort().join('+'); }}

function updateDeadDisplay() {{
  document.querySelectorAll('.key-dead').forEach(btn => {{
    btn.classList.toggle('active', deadMods.has(btn.dataset.mod));
  }});
  const composeEl = document.getElementById('compose-status');
  if (deadMods.size > 0) {{
    composeEl.textContent = 'composing: ' + [...deadMods].sort().join(' + ');
  }} else {{
    composeEl.textContent = '';
  }}
}}

function insertComposed(keyUpper) {{
  const modKey = composeKey();
  deadMods.clear();
  updateDeadDisplay();
  if (!modKey) return null; // no mods — not a compose attempt
  const composed = COMPOSE[modKey + '|' + keyUpper];
  if (composed) return composed;
  // Fall back: base letter + combining diacritics
  const base = KEY_MAP[keyUpper];
  if (!base) return null;
  const mods = modKey.split('+');
  return base + mods.map(m => COMBINING[m] || '').join('');
}}

function insertAt(ch) {{
  const s = ta.selectionStart, e = ta.selectionEnd;
  ta.value = ta.value.slice(0, s) + ch + ta.value.slice(e);
  ta.selectionStart = ta.selectionEnd = s + ch.length;
  scheduleAutosave();
}}

// ── Textarea keydown ──
const VOWELS = new Set(['A','E','H','I','O','Y','W','R']); // R for ῥ

ta.addEventListener('keydown', e => {{
  if (e.ctrlKey || e.altKey || e.metaKey) return;
  if (['Backspace','Delete','Enter','Tab','Escape',
       'ArrowUp','ArrowDown','ArrowLeft','ArrowRight',
       'Home','End','PageUp','PageDown'].includes(e.key)) return;

  const k = e.key;
  const kUpper = k.toUpperCase();

  // Dead key?
  if (DEAD_KEYS[k] !== undefined) {{
    e.preventDefault();
    const mod = DEAD_KEYS[k];
    deadMods.has(mod) ? deadMods.delete(mod) : deadMods.add(mod);
    updateDeadDisplay();
    return;
  }}

  // If dead mods are active, try compose
  if (deadMods.size > 0) {{
    e.preventDefault();
    const ch = insertComposed(kUpper);
    if (ch) insertAt(ch);
    return;
  }}

  // Regular letter/punctuation
  const ch = KEY_MAP[kUpper] || KEY_MAP[k];
  if (ch) {{ e.preventDefault(); insertAt(ch); }}
}});

// ── Virtual keyboard clicks ──
document.querySelectorAll('.key[data-char]').forEach(btn => {{
  btn.addEventListener('mousedown', e => {{
    e.preventDefault();
    if (deadMods.size > 0) {{
      // Try to compose with the letter
      const greek = btn.dataset.char;
      // Find the KEY_MAP key for this greek char
      const kUpper = Object.entries(KEY_MAP).find(([,v]) => v === greek)?.[0];
      if (kUpper) {{
        const composed = insertComposed(kUpper);
        if (composed) {{ insertAt(composed); return; }}
      }}
      deadMods.clear(); updateDeadDisplay();
    }}
    insertAt(btn.dataset.char);
  }});
}});

document.querySelectorAll('.key-dead').forEach(btn => {{
  btn.addEventListener('mousedown', e => {{
    e.preventDefault();
    const mod = btn.dataset.mod;
    deadMods.has(mod) ? deadMods.delete(mod) : deadMods.add(mod);
    updateDeadDisplay();
    ta.focus();
  }});
}});

document.getElementById('btn-clear-mods').addEventListener('mousedown', e => {{
  e.preventDefault(); deadMods.clear(); updateDeadDisplay(); ta.focus();
}});

document.getElementById('btn-bksp').addEventListener('mousedown', e => {{
  e.preventDefault();
  const s = ta.selectionStart, en = ta.selectionEnd;
  if (s === en && s > 0) {{
    ta.value = ta.value.slice(0, s - 1) + ta.value.slice(s);
    ta.selectionStart = ta.selectionEnd = s - 1;
  }} else if (s !== en) {{
    ta.value = ta.value.slice(0, s) + ta.value.slice(en);
    ta.selectionStart = ta.selectionEnd = s;
  }}
  scheduleAutosave();
}});

// ── Image zoom via slider ──
const imgPane  = document.getElementById('img-pane');
const img      = document.getElementById('folio-img');
const slider   = document.getElementById('zoom-slider');
const zoomLbl  = document.getElementById('zoom-label');
let naturalW   = 0;

function applyZoom(pct) {{
  pct = Math.max(10, Math.min(400, pct));
  if (naturalW) img.style.width = (naturalW * pct / 100) + 'px';
  slider.value = pct;
  zoomLbl.textContent = pct + '%';
}}

img.addEventListener('load', () => {{
  naturalW = img.naturalWidth;
  applyZoom(Math.round(imgPane.clientWidth / naturalW * 100));
}});

slider.addEventListener('input', () => applyZoom(parseInt(slider.value)));

document.getElementById('btn-zoom-fit').addEventListener('click', () => {{
  if (naturalW) applyZoom(Math.round(imgPane.clientWidth / naturalW * 100));
}});
document.getElementById('btn-zoom-100').addEventListener('click', () => applyZoom(100));

ta.focus();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

def make_handler(manuscript: str, manuscript_dir: Path, folios: list[str]) -> type:

    class Handler(BaseHTTPRequestHandler):

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            qs     = parse_qs(parsed.query)
            folio  = qs.get("folio", [folios[0] if folios else ""])[0]
            p      = parsed.path

            if p == "/":
                html = generate_html(manuscript, folio, folios).encode("utf-8")
                self._send(200, html, "text/html; charset=utf-8")
            elif p == "/image":
                self._serve_image(manuscript_dir, folio)
            elif p == "/ocr":
                self._serve_file(manuscript_dir / "transcripts" / f"{folio}.json")
            elif p == "/manual":
                self._serve_file(manuscript_dir / "transcriptions" / f"{folio}_manual.json")
            elif p == "/folios":
                self._send(200, json.dumps(folios).encode(), "application/json")
            else:
                self.send_error(404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            qs     = parse_qs(parsed.query)
            folio  = qs.get("folio", [""])[0]

            if parsed.path == "/manual" and folio:
                length  = int(self.headers.get("Content-Length", 0))
                body    = self.rfile.read(length)
                payload = json.loads(body)
                payload["saved_at"] = datetime.now().isoformat()
                out = manuscript_dir / "transcriptions" / f"{folio}_manual.json"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                self._send(200, b'{"ok":true}', "application/json")
            else:
                self.send_error(404)

        def _serve_image(self, mdir: Path, folio: str) -> None:
            images_dir = mdir / "images"
            candidates = list(images_dir.glob(f"{folio}.*")) if images_dir.exists() else []
            if not candidates:
                self.send_error(404)
                return
            path   = candidates[0]
            suffix = path.suffix.lower().lstrip(".")
            mime   = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                      "png": "image/png", "tif": "image/tiff"}.get(suffix, "image/jpeg")
            self._send(200, path.read_bytes(), mime)

        def _serve_file(self, path: Path) -> None:
            if path.exists():
                self._send(200, path.read_bytes(), "application/json")
            else:
                self._send(200, b"null", "application/json")

        def _send(self, code: int, body: bytes, ct: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            pass

    return Handler


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manual transcription web interface for manuscript folios.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Dead-key diacritics (press before a vowel):
  [  smooth breathing (ψιλή)        ]  rough breathing (δασεῖα)
  '  acute accent (ὀξεῖα)           `  grave accent (βαρεῖα)
  =  circumflex (περισπωμένη)        \\  iota subscript
  |  dieresis

  Combine: [' A → ἄ   ]' A → ἅ   =[ A → ἆ   etc.

Letter map:
  Q=Θ  W=Ω  E=Ε  R=Ρ  T=Τ  Y=Υ  U=Ϲ  I=Ι  O=Ο  P=Π
  A=Α  S=Σ  D=Δ  F=Φ  G=Γ  H=Η  J=Ξ  K=Κ  L=Λ
  Z=Ζ  X=Χ  C=Ψ  V=Β  N=Ν  M=Μ
  ;=·  :=÷
        """,
    )
    parser.add_argument("--manuscript", required=True, metavar="ID")
    parser.add_argument("--folio",      required=True, metavar="FOLIO")
    parser.add_argument("--port",       type=int, default=_DEFAULT_PORT, metavar="PORT")
    args = parser.parse_args()

    manuscript_dir = _MANUSCRIPTS / args.manuscript
    if not manuscript_dir.exists():
        print(f"ERROR: manuscript directory not found: {manuscript_dir}", file=sys.stderr)
        sys.exit(1)

    folios = _list_folios(manuscript_dir)
    if not folios:
        print(f"ERROR: no images found in {manuscript_dir / 'images'}", file=sys.stderr)
        sys.exit(1)
    if args.folio not in folios:
        print(f"WARNING: folio '{args.folio}' not in image list; it will load but navigation may be incomplete.")

    handler_cls = make_handler(args.manuscript, manuscript_dir, folios)
    server      = HTTPServer(("127.0.0.1", args.port), handler_cls)
    url         = f"http://127.0.0.1:{args.port}/?folio={args.folio}"

    print(f"Manuscript : {args.manuscript}")
    print(f"Folio      : {args.folio}  ({folios.index(args.folio)+1}/{len(folios)})")
    print(f"Folios     : {folios[:5]}{'…' if len(folios)>5 else ''}")
    print(f"Server     : {url}")
    print("Press Ctrl-C to stop.\n")

    threading.Thread(target=lambda: (
        __import__("time").sleep(0.4),
        webbrowser.open(url),
    ), daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
