"""Generate a standalone HTML labeling interface from an OCR transcript.

Reads  data/manuscripts/{id}/transcripts/{folio}.json
Writes data/manuscripts/{id}/labels/{folio}.html

Usage:
    python scripts/label_ocr.py --manuscript vat.gr.1209 --folio 41

Or pass --label when running the OCR pipeline and it will be called automatically:
    python -m src.ocr.recognize --manuscript vat.gr.1209 --folio 41 --save --label

Features of the generated HTML (self-contained, no server):
  - Manuscript image on the left with a canvas overlay
  - Colored bounding boxes per line, labeled with line number and column
  - Character-level boxes shown on hover/selection (thin ticks per character)
  - Side panel with editable transcription fields, one per line
  - Column badges (Col 1 / Col 2 / Col 3) for multi-column manuscripts
  - Confidence color coding: green ≥85%, yellow 65–85%, red <65%
  - Click line row  → highlight box on image, scroll image to it
  - Click canvas   → select nearest line box
  - Skip button    → mark line unreadable
  - Export button  → download corrected JSON (Kraken ground-truth ready)
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_DATA = _ROOT / "data"
_MANUSCRIPTS = _DATA / "manuscripts"

_COL_COLORS = [
    "rgba(59,130,246,{a})",    # blue — col 0
    "rgba(168,85,247,{a})",    # purple — col 1
    "rgba(20,184,166,{a})",    # teal — col 2
    "rgba(249,115,22,{a})",    # orange — col 3
]
_COL_CSS = ["#3b82f6", "#a855f7", "#14b8a6", "#f97316"]


def _conf_fill(conf: float | None) -> str:
    if conf is None:
        return "rgba(100,100,255,0.30)"
    if conf >= 0.85:
        return "rgba(34,197,94,0.35)"
    if conf >= 0.65:
        return "rgba(234,179,8,0.35)"
    return "rgba(239,68,68,0.35)"


def _image_as_data_url(image_path: Path) -> str:
    suffix = image_path.suffix.lower().lstrip(".")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png",
            "tif": "tiff", "tiff": "tiff"}.get(suffix, "jpeg")
    data = base64.b64encode(image_path.read_bytes()).decode()
    return f"data:image/{mime};base64,{data}"


def generate_html(
    manuscript: str,
    folio: str,
    ocr_json: dict,
    image_path: Path,
    result_idx: int = 0,
) -> str:
    result = ocr_json["results"][result_idx]
    lines = result.get("lines", [])
    engine = result["engine"]
    img_w, img_h = ocr_json["preprocessing"]["original_size"]

    num_cols = max((ln.get("column", 0) for ln in lines), default=0) + 1

    image_data_url = _image_as_data_url(image_path)
    lines_json = json.dumps(lines, ensure_ascii=False)
    fill_colors  = json.dumps([_conf_fill(ln.get("confidence")) for ln in lines])
    col_css_json = json.dumps(_COL_CSS)

    col_badges_html = "".join(
        f'<span class="col-badge" style="background:{_COL_CSS[i % len(_COL_CSS)]}22;'
        f'border-color:{_COL_CSS[i % len(_COL_CSS)]}88;color:{_COL_CSS[i % len(_COL_CSS)]}">'
        f'Col {i + 1}</span>'
        for i in range(num_cols)
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Label — {manuscript} f.{folio}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0c111d;color:#e2e8f0;height:100vh;display:flex;flex-direction:column}}
  #hdr{{padding:8px 14px;background:#111827;border-bottom:1px solid #1f2937;display:flex;align-items:center;gap:12px;flex-shrink:0}}
  #hdr h1{{font-size:14px;font-weight:600;color:#f1f5f9}}
  .meta{{font-size:11px;color:#6b7280}}
  .col-badge{{font-size:10px;font-weight:600;padding:2px 6px;border-radius:4px;border:1px solid}}
  #hdr .actions{{margin-left:auto;display:flex;gap:6px}}
  button{{padding:4px 11px;border-radius:5px;border:none;cursor:pointer;font-size:12px;font-weight:500}}
  #btn-chars{{background:#1f2937;color:#94a3b8}}
  #btn-chars.active{{background:#374151;color:#e2e8f0}}
  #btn-export{{background:#2563eb;color:white}}
  #btn-export:hover{{background:#1d4ed8}}
  #btn-edit{{background:#1f2937;color:#94a3b8}}
  #btn-edit.active{{background:#78350f;color:#fde68a}}
  #main{{display:flex;flex:1;overflow:hidden}}

  /* viewer */
  #viewer{{flex:1;overflow:auto;background:#020617;position:relative}}
  #canvas-wrap{{position:relative;display:inline-block}}
  #img-bg{{display:block}}
  #overlay{{position:absolute;top:0;left:0;cursor:crosshair}}

  /* panel */
  #panel{{width:370px;flex-shrink:0;display:flex;flex-direction:column;border-left:1px solid #1f2937}}
  #phdr{{padding:8px 10px;background:#111827;font-size:11px;color:#6b7280;border-bottom:1px solid #1f2937;display:flex;justify-content:space-between}}
  #line-list{{flex:1;overflow-y:auto}}
  .row{{display:flex;align-items:flex-start;gap:6px;padding:5px 8px;border-bottom:1px solid #1a2234;cursor:pointer}}
  .row:hover{{background:#111827}}
  .row.sel{{background:#0f2544;border-left:3px solid #3b82f6}}
  .row.skp{{opacity:0.38}}
  .lnum{{font-size:10px;color:#4b5563;width:22px;text-align:right;flex-shrink:0;padding-top:3px}}
  .cdot{{width:7px;height:7px;border-radius:50%;flex-shrink:0;margin-top:5px}}
  .cbadge{{font-size:9px;padding:1px 4px;border-radius:3px;flex-shrink:0;margin-top:3px;font-weight:600}}
  .line-ta{{flex:1;background:transparent;border:none;color:#e2e8f0;font-size:13px;font-family:"Noto Serif","Times New Roman",Georgia,serif;resize:none;outline:none;line-height:1.5;min-height:18px}}
  .line-ta:focus{{background:rgba(255,255,255,0.03);border-radius:3px}}
  .skip-x{{flex-shrink:0;font-size:10px;padding:2px 5px;border-radius:3px;background:#1f2937;color:#6b7280;border:none;cursor:pointer;margin-top:2px}}
  .row.skp .skip-x{{background:#450a0a;color:#f87171}}
  .legend{{padding:6px 10px;border-top:1px solid #1f2937;display:flex;gap:10px;font-size:10px;color:#6b7280;flex-wrap:wrap}}
  .legend span{{display:flex;align-items:center;gap:3px}}
  .ldot{{width:7px;height:7px;border-radius:50%}}
</style>
</head>
<body>
<div id="hdr">
  <h1>OCR Labeling</h1>
  <div class="meta">{manuscript} · folio {folio} · {engine} · {len(lines)} lines</div>
  {col_badges_html}
  <div class="actions">
    <button id="btn-chars" title="Toggle character-level boxes">Chars</button>
    <button id="btn-edit" title="Edit bounding boxes — drag to move/resize · draw to add · Delete to remove">Edit Boxes</button>
    <button id="btn-export">Export JSON</button>
  </div>
</div>
<div id="main">
  <div id="viewer">
    <div id="canvas-wrap">
      <img id="img-bg" src="{image_data_url}" style="max-width:100%">
      <canvas id="overlay"></canvas>
    </div>
  </div>
  <div id="panel">
    <div id="phdr"><span>Transcription</span><span id="sel-info">click a line or box</span></div>
    <div id="line-list"></div>
    <div class="legend">
      <span><span class="ldot" style="background:#22c55e"></span>≥85%</span>
      <span><span class="ldot" style="background:#eab308"></span>65–85%</span>
      <span><span class="ldot" style="background:#ef4444"></span>&lt;65%</span>
      <span><span class="ldot" style="background:#6464ff"></span>n/a</span>
    </div>
  </div>
</div>
<script>
const LINES      = {lines_json};
const FILLS      = {fill_colors};
const COL_CSS    = {col_css_json};
const IMG_W      = {img_w};
const IMG_H      = {img_h};
const MANUSCRIPT = {json.dumps(manuscript)};
const FOLIO      = {json.dumps(folio)};

// ── Mutable state ──
let selIdx    = -1;
let showChars = false;
let editMode  = false;
let dragState = null;  // active drag: {{type,lineIdx,handle,startX,startY,startBbox}} | {{type:'draw',...}}
const skipped    = new Set();
const deleted    = new Set();
const texts      = LINES.map(l => l.text);
const bboxes     = LINES.map(l => l.bbox ? [...l.bbox] : null);  // mutable per-line bbox
const extraLines = [];   // {{bbox,column,chars}} — lines drawn in edit mode
const extraTexts = [];
const HSIZE = 5;         // handle half-size in canvas px

// ── Bbox helpers ──
function getBbox(i) {{
  if (i < LINES.length) return bboxes[i];
  const el = extraLines[i - LINES.length];
  return el ? el.bbox : null;
}}
function setBbox(i, v) {{
  if (i < LINES.length) {{ bboxes[i] = v; return; }}
  const el = extraLines[i - LINES.length];
  if (el) el.bbox = v;
}}
function totalLines() {{ return LINES.length + extraLines.length; }}

// ── Resize handle helpers ──
function getHandles(bbox, s) {{
  if (!bbox || bbox.length < 4) return [];
  const [x1,y1,x2,y2] = bbox.map(v => v*s);
  const mx=(x1+x2)/2, my=(y1+y2)/2;
  return [
    {{id:'tl',x:x1,y:y1,cx:-1,cy:-1,cur:'nwse-resize'}},
    {{id:'tm',x:mx,y:y1,cx:0, cy:-1,cur:'ns-resize'}},
    {{id:'tr',x:x2,y:y1,cx:1, cy:-1,cur:'nesw-resize'}},
    {{id:'ml',x:x1,y:my,cx:-1,cy:0, cur:'ew-resize'}},
    {{id:'mr',x:x2,y:my,cx:1, cy:0, cur:'ew-resize'}},
    {{id:'bl',x:x1,y:y2,cx:-1,cy:1, cur:'nesw-resize'}},
    {{id:'bm',x:mx,y:y2,cx:0, cy:1, cur:'ns-resize'}},
    {{id:'br',x:x2,y:y2,cx:1, cy:1, cur:'nwse-resize'}},
  ];
}}
function hitHandle(bbox, mx, my, s) {{
  for (const h of getHandles(bbox, s))
    if (Math.abs(mx-h.x) <= HSIZE+3 && Math.abs(my-h.y) <= HSIZE+3) return h;
  return null;
}}
function hitBox(bbox, mx, my, s) {{
  if (!bbox || bbox.length < 4) return false;
  const [x1,y1,x2,y2] = bbox.map(v => v*s);
  return mx>=x1 && mx<=x2 && my>=y1 && my<=y2;
}}

// ── Row factory ──
const listEl = document.getElementById('line-list');
function makeRow(i, text, conf, col) {{
  const dotClr = conf===null ? '#6464ff'
    : conf>=0.85 ? '#22c55e' : conf>=0.65 ? '#eab308' : '#ef4444';
  const colClr = COL_CSS[col % COL_CSS.length];
  const confTip = conf!==null ? `${{(conf*100).toFixed(1)}}%` : 'n/a';
  const row = document.createElement('div');
  row.className = 'row';
  row.dataset.idx = i;
  row.innerHTML = `
    <span class="lnum">${{i+1}}</span>
    <span class="cdot" style="background:${{dotClr}}" title="conf ${{confTip}}"></span>
    <span class="cbadge" style="background:${{colClr}}22;color:${{colClr}};border:1px solid ${{colClr}}55"
          title="Column ${{col+1}}">C${{col+1}}</span>
    <textarea class="line-ta" rows="1" spellcheck="false">${{esc(text)}}</textarea>
    <button class="skip-x" title="Mark unreadable">✕</button>
  `;
  const ta = row.querySelector('textarea');
  ta.addEventListener('input', () => {{
    if (i < LINES.length) texts[i] = ta.value;
    else extraTexts[i - LINES.length] = ta.value;
    grow(ta);
  }});
  ta.addEventListener('focus', () => selectLine(i, false));
  grow(ta);
  row.querySelector('.skip-x').addEventListener('click', e => {{ e.stopPropagation(); toggleSkip(i); }});
  row.addEventListener('click', () => selectLine(i));
  return row;
}}
LINES.forEach((ln, i) => {{
  listEl.appendChild(makeRow(i, ln.text, ln.confidence, ln.column||0));
}});

function esc(s) {{
  return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}
function grow(ta) {{
  ta.style.height = 'auto';
  ta.style.height = ta.scrollHeight + 'px';
}}
function toggleSkip(i) {{
  skipped.has(i) ? skipped.delete(i) : skipped.add(i);
  listEl.children[i].classList.toggle('skp', skipped.has(i));
  draw();
}}

// ── Canvas ──
const img    = document.getElementById('img-bg');
const canvas = document.getElementById('overlay');
const ctx    = canvas.getContext('2d');
function sc() {{ return img.clientWidth / IMG_W; }}

// ── Draw ──
function draw() {{
  const s = sc();
  canvas.width  = img.clientWidth;
  canvas.height = img.clientHeight;

  for (let i = 0; i < totalLines(); i++) {{
    if (deleted.has(i)) continue;
    const bbox = getBbox(i);
    if (!bbox || bbox.length < 4) continue;

    let col, conf, chars;
    if (i < LINES.length) {{
      col = LINES[i].column || 0; conf = LINES[i].confidence; chars = LINES[i].chars || [];
    }} else {{
      const el = extraLines[i - LINES.length];
      col = el.column || 0; conf = null; chars = [];
    }}

    const [x1,y1,x2,y2] = bbox.map(v => Math.round(v*s));
    const colClr = COL_CSS[col % COL_CSS.length];
    const isSel  = i === selIdx;

    if (skipped.has(i)) {{
      ctx.fillStyle = 'rgba(127,0,0,0.20)'; ctx.strokeStyle = 'rgba(200,50,50,0.50)'; ctx.lineWidth = 1;
    }} else if (isSel) {{
      ctx.fillStyle = 'rgba(59,130,246,0.25)'; ctx.strokeStyle = '#60a5fa'; ctx.lineWidth = 2;
    }} else {{
      ctx.fillStyle = i < FILLS.length ? FILLS[i] : 'rgba(100,100,255,0.30)';
      ctx.strokeStyle = colClr+'66'; ctx.lineWidth = 1;
    }}
    ctx.fillRect(x1,y1,x2-x1,y2-y1);
    ctx.strokeRect(x1,y1,x2-x1,y2-y1);

    ctx.font = `bold ${{Math.max(9,Math.round(9*s))}}px sans-serif`;
    ctx.fillStyle = isSel ? '#93c5fd' : colClr+'cc';
    ctx.fillText(i+1, x1+2, y1+Math.max(10,Math.round(12*s)));

    if ((isSel || showChars) && chars.length > 0) {{
      chars.forEach(ch => {{
        const cx1=Math.round(ch.x1*s), cy1=Math.round(ch.y1*s), cy2=Math.round(ch.y2*s);
        const chConf = ch.confidence;
        const chClr = chConf===null ? 'rgba(150,150,255,0.7)'
          : chConf>=0.85 ? 'rgba(34,197,94,0.8)'
          : chConf>=0.65 ? 'rgba(234,179,8,0.8)' : 'rgba(239,68,68,0.8)';
        ctx.strokeStyle=chClr; ctx.lineWidth=1;
        ctx.beginPath(); ctx.moveTo(cx1,cy1); ctx.lineTo(cx1,cy2); ctx.stroke();
        if (isSel && ch.char && ch.char.trim()) {{
          ctx.font = `${{Math.max(7,Math.round(8*s))}}px serif`;
          ctx.fillStyle = chClr;
          ctx.fillText(ch.char, cx1, cy1-2);
        }}
      }});
    }}

    // Edit mode: draw resize handles on selected line
    if (editMode && isSel) {{
      for (const h of getHandles(bbox, s)) {{
        ctx.fillStyle='#f8fafc'; ctx.strokeStyle='#3b82f6'; ctx.lineWidth=1.5;
        ctx.fillRect(h.x-HSIZE, h.y-HSIZE, HSIZE*2, HSIZE*2);
        ctx.strokeRect(h.x-HSIZE, h.y-HSIZE, HSIZE*2, HSIZE*2);
      }}
    }}
  }}

  // Preview while drawing a new box
  if (dragState && dragState.type==='draw') {{
    const {{startX:sx,startY:sy,curX:cx,curY:cy}} = dragState;
    ctx.fillStyle='rgba(251,191,36,0.15)'; ctx.strokeStyle='#fbbf24'; ctx.lineWidth=1.5;
    ctx.setLineDash([4,4]);
    ctx.fillRect(Math.min(sx,cx),Math.min(sy,cy),Math.abs(cx-sx),Math.abs(cy-sy));
    ctx.strokeRect(Math.min(sx,cx),Math.min(sy,cy),Math.abs(cx-sx),Math.abs(cy-sy));
    ctx.setLineDash([]);
  }}
}}

new ResizeObserver(draw).observe(img);
img.addEventListener('load', draw);
draw();

// ── Canvas events ──
canvas.addEventListener('mousemove', e => {{
  const r = canvas.getBoundingClientRect();
  const mx=e.clientX-r.left, my=e.clientY-r.top;
  const s=sc();

  if (dragState) {{
    const dx=mx-dragState.startX, dy=my-dragState.startY;
    if (dragState.type==='move') {{
      const [bx1,by1,bx2,by2] = dragState.startBbox;
      setBbox(dragState.lineIdx, [bx1+dx/s, by1+dy/s, bx2+dx/s, by2+dy/s]);
    }} else if (dragState.type==='resize') {{
      const h=dragState.handle;
      let [bx1,by1,bx2,by2] = dragState.startBbox;
      if (h.cx<0) bx1+=dx/s; if (h.cx>0) bx2+=dx/s;
      if (h.cy<0) by1+=dy/s; if (h.cy>0) by2+=dy/s;
      setBbox(dragState.lineIdx, [
        Math.min(bx1,bx2), Math.min(by1,by2), Math.max(bx1,bx2), Math.max(by1,by2)
      ]);
    }} else if (dragState.type==='draw') {{
      dragState.curX=mx; dragState.curY=my;
    }}
    draw(); return;
  }}

  if (!editMode) return;
  let cur='crosshair';
  if (selIdx>=0) {{
    const h=hitHandle(getBbox(selIdx),mx,my,s);
    if (h) {{ cur=h.cur; }}
    else if (hitBox(getBbox(selIdx),mx,my,s)) {{ cur='move'; }}
  }}
  if (cur==='crosshair') {{
    for (let i=0; i<totalLines(); i++) {{
      if (deleted.has(i)) continue;
      if (hitBox(getBbox(i),mx,my,s)) {{ cur='move'; break; }}
    }}
  }}
  canvas.style.cursor=cur;
}});

canvas.addEventListener('mousedown', e => {{
  const r = canvas.getBoundingClientRect();
  const mx=e.clientX-r.left, my=e.clientY-r.top;
  const s=sc();

  if (!editMode) {{
    // Normal: select nearest line
    let best=-1, bestArea=Infinity;
    for (let i=0; i<totalLines(); i++) {{
      if (deleted.has(i)) continue;
      const bbox=getBbox(i);
      if (hitBox(bbox,mx,my,s)) {{
        const [x1,y1,x2,y2]=bbox.map(v=>v*s);
        const a=(x2-x1)*(y2-y1);
        if (a<bestArea) {{ bestArea=a; best=i; }}
      }}
    }}
    if (best>=0) selectLine(best);
    return;
  }}

  e.preventDefault();

  // Edit mode: resize handle on selected line?
  if (selIdx>=0) {{
    const h=hitHandle(getBbox(selIdx),mx,my,s);
    if (h) {{
      dragState={{type:'resize',lineIdx:selIdx,handle:h,
                  startX:mx,startY:my,startBbox:[...getBbox(selIdx)]}};
      return;
    }}
  }}

  // Move any box
  let best=-1, bestArea=Infinity;
  for (let i=0; i<totalLines(); i++) {{
    if (deleted.has(i)) continue;
    const bbox=getBbox(i);
    if (hitBox(bbox,mx,my,s)) {{
      const [x1,y1,x2,y2]=bbox.map(v=>v*s);
      const a=(x2-x1)*(y2-y1);
      if (a<bestArea) {{ bestArea=a; best=i; }}
    }}
  }}
  if (best>=0) {{
    selectLine(best);
    dragState={{type:'move',lineIdx:best,
                startX:mx,startY:my,startBbox:[...getBbox(best)]}};
    return;
  }}

  // Draw new box on empty space
  dragState={{type:'draw',startX:mx,startY:my,curX:mx,curY:my}};
}});

canvas.addEventListener('mouseup', e => {{
  if (!dragState) return;
  if (dragState.type==='draw') {{
    const r=canvas.getBoundingClientRect();
    const mx=e.clientX-r.left, my=e.clientY-r.top;
    const s=sc();
    const x1=Math.min(dragState.startX,mx)/s, y1=Math.min(dragState.startY,my)/s;
    const x2=Math.max(dragState.startX,mx)/s, y2=Math.max(dragState.startY,my)/s;
    if ((x2-x1)>10 && (y2-y1)>5) {{
      const newIdx=LINES.length+extraLines.length;
      extraLines.push({{bbox:[x1,y1,x2,y2],column:0,chars:[]}});
      extraTexts.push('');
      listEl.appendChild(makeRow(newIdx,'',null,0));
      selectLine(newIdx);
    }}
  }}
  dragState=null; draw();
}});

canvas.addEventListener('mouseleave', () => {{
  if (dragState && dragState.type==='draw') {{ dragState=null; draw(); }}
}});

// Delete/Backspace removes selected line (edit mode only, not while in textarea)
document.addEventListener('keydown', e => {{
  if (!editMode || selIdx<0) return;
  if (e.key!=='Delete' && e.key!=='Backspace') return;
  if (document.activeElement && document.activeElement.tagName==='TEXTAREA') return;
  e.preventDefault();
  deleted.add(selIdx);
  const row=listEl.children[selIdx];
  if (row) {{ row.style.opacity='0.2'; row.style.textDecoration='line-through'; }}
  draw();
}});

function selectLine(i, scrollImg=true) {{
  selIdx=i;
  Array.from(listEl.children).forEach((r,j) => r.classList.toggle('sel',j===i));
  const row=listEl.children[i];
  if (row) {{
    row.scrollIntoView({{block:'nearest'}});
    const ta=row.querySelector('textarea');
    if (ta) ta.focus();
  }}
  let col=0, conf=null;
  if (i<LINES.length) {{ col=LINES[i].column||0; conf=LINES[i].confidence; }}
  else {{ const el=extraLines[i-LINES.length]; if(el) col=el.column||0; }}
  document.getElementById('sel-info').textContent=
    `Line ${{i+1}} · C${{col+1}} · ${{conf!==null ? (conf*100).toFixed(1)+'%' : 'n/a'}}`;
  if (scrollImg) {{
    const bbox=getBbox(i);
    if (bbox && bbox.length>=4) {{
      const s=sc();
      const mid=((bbox[1]+bbox[3])/2)*s - document.getElementById('viewer').clientHeight/2;
      document.getElementById('viewer').scrollTop=Math.max(0,mid);
    }}
  }}
  draw();
}}

document.getElementById('btn-chars').addEventListener('click', function() {{
  showChars=!showChars; this.classList.toggle('active',showChars); draw();
}});

document.getElementById('btn-edit').addEventListener('click', function() {{
  editMode=!editMode;
  this.classList.toggle('active',editMode);
  canvas.style.cursor=editMode ? 'crosshair' : 'crosshair';
  draw();
}});

document.getElementById('btn-export').addEventListener('click', () => {{
  const lines=[];
  for (let i=0; i<totalLines(); i++) {{
    const origText = i<LINES.length ? LINES[i].text : '';
    const curText  = i<LINES.length ? texts[i] : (extraTexts[i-LINES.length]||'');
    lines.push({{
      bbox:          getBbox(i),
      column:        i<LINES.length ? (LINES[i].column||0) : (extraLines[i-LINES.length]?.column||0),
      text:          curText,
      original_text: origText,
      corrected:     curText !== origText,
      skip:          skipped.has(i),
      deleted:       deleted.has(i),
      is_new:        i >= LINES.length,
      confidence:    i<LINES.length ? LINES[i].confidence : null,
      chars:         i<LINES.length ? (LINES[i].chars||[]) : [],
    }});
  }}
  const payload={{
    manuscript:MANUSCRIPT, folio:FOLIO, lines,
    stats:{{
      total:     lines.filter(l=>!l.deleted).length,
      corrected: lines.filter(l=>l.corrected&&!l.deleted).length,
      skipped:   lines.filter(l=>l.skip&&!l.deleted).length,
      deleted:   lines.filter(l=>l.deleted).length,
      added:     lines.filter(l=>l.is_new&&!l.deleted).length,
    }},
  }};
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{{type:'application/json'}}));
  a.download=`${{MANUSCRIPT}}_f${{FOLIO}}_labeled.json`;
  a.click();
}});
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate OCR labeling HTML from transcript JSON.")
    parser.add_argument("--manuscript", required=True, metavar="ID")
    parser.add_argument("--folio", required=True, metavar="FOLIO")
    parser.add_argument("--result-idx", type=int, default=0, metavar="N",
                        help="Which result entry to label if multiple engines ran (default: 0)")
    args = parser.parse_args()

    manuscript_dir = _MANUSCRIPTS / args.manuscript
    transcript_path = manuscript_dir / "transcripts" / f"{args.folio}.json"

    # Fallback: old path used before the folder restructure
    if not transcript_path.exists():
        old_path = manuscript_dir / "ocr" / f"{args.folio}.json"
        if old_path.exists():
            transcript_path = old_path
        else:
            print(f"ERROR: transcript not found: {transcript_path}", file=sys.stderr)
            print("Run OCR first:", file=sys.stderr)
            print(f"  python -m src.ocr.recognize --manuscript {args.manuscript} "
                  f"--folio {args.folio} --save", file=sys.stderr)
            sys.exit(1)

    ocr_data = json.loads(transcript_path.read_text(encoding="utf-8"))

    image_path = Path(ocr_data.get("image", ""))
    if not image_path.exists():
        images_dir = manuscript_dir / "images"
        candidates = list(images_dir.glob(f"{args.folio}.*"))
        if not candidates:
            print(f"ERROR: image for folio {args.folio} not found", file=sys.stderr)
            sys.exit(1)
        image_path = candidates[0]

    n_results = len(ocr_data.get("results", []))
    if args.result_idx >= n_results:
        print(f"ERROR: result_idx {args.result_idx} out of range", file=sys.stderr)
        sys.exit(1)

    result = ocr_data["results"][args.result_idx]
    n_lines = len(result.get("lines", []))
    print(f"Manuscript: {args.manuscript}  folio: {args.folio}")
    print(f"Engine:     {result['engine']}  ·  {n_lines} lines")
    print(f"Image:      {image_path}  ({image_path.stat().st_size // 1024} KB)")
    print("Embedding image…")

    html = generate_html(
        manuscript=args.manuscript,
        folio=args.folio,
        ocr_json=ocr_data,
        image_path=image_path,
        result_idx=args.result_idx,
    )

    labels_dir = manuscript_dir / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)
    out_path = labels_dir / f"{args.folio}.html"
    out_path.write_text(html, encoding="utf-8")

    size_kb = out_path.stat().st_size // 1024
    print(f"Label HTML: {out_path}  ({size_kb} KB)")
    print("Open in any browser — no server needed.")


if __name__ == "__main__":
    main()
