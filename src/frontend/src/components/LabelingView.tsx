import { useCallback, useEffect, useRef, useState } from 'react'
import VirtualKeyboard from './VirtualKeyboard'

// ── Types ─────────────────────────────────────────────────────────────────────

interface CharBox {
  id: number
  bbox: [number, number, number, number]
  ocr_char: string | null
  unicode_label: string | null
  ocr_confidence: number | null
}

interface Sample {
  id: number
  manuscript: string
  folio: string
  hand_id: 'a' | 'b' | 'unknown'
  line_image_path: string
  image_url: string
  ocr_guess: string | null
  ground_truth: string | null
  status: 'pending' | 'confirmed' | 'skipped'
  column_index: number | null
  chars: CharBox[]
}

interface Stats {
  [hand: string]: { total: number; confirmed: number; skipped: number; pending: number }
}

type LabelMode = 'line' | 'char'
type Handle = 'nw' | 'n' | 'ne' | 'w' | 'e' | 'sw' | 's' | 'se' | 'move'

// ── API helpers ───────────────────────────────────────────────────────────────

async function apiFetch(url: string, opts?: RequestInit) {
  const res = await fetch(url, opts)
  if (!res.ok) throw new Error(`${opts?.method ?? 'GET'} ${url} → ${res.status} ${res.statusText}`)
  if (res.status === 204) return null
  return res.json()
}

const fetchSamples    = (hand: string) =>
  apiFetch(`/api/training/lines?hand=${hand}&status=pending&limit=500`)
const fetchSample     = (id: number) =>
  apiFetch(`/api/training/lines/${id}`)
const postLabel       = (id: number, gt: string) =>
  apiFetch(`/api/training/lines/${id}/label`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ground_truth: gt }),
  })
const postSkip        = (id: number) =>
  apiFetch(`/api/training/lines/${id}/skip`, { method: 'POST' })
const postCharLabel   = (charId: number, label: string) =>
  apiFetch(`/api/training/chars/${charId}/label`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ unicode_label: label }),
  })
const postDetectChars = (id: number) =>
  apiFetch(`/api/training/lines/${id}/detect-chars`, { method: 'POST' })
const patchBbox       = (charId: number, bbox: [number, number, number, number]) =>
  apiFetch(`/api/training/chars/${charId}/bbox`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bbox }),
  })
const postAddChar     = (sampleId: number, bbox: [number, number, number, number]) =>
  apiFetch(`/api/training/lines/${sampleId}/chars`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bbox }),
  })
const deleteCharApi   = (charId: number) =>
  apiFetch(`/api/training/chars/${charId}`, { method: 'DELETE' })
const fetchStats      = () => apiFetch('/api/training/stats')

// ── BboxEditor ────────────────────────────────────────────────────────────────

const HANDLE_POS: Record<Exclude<Handle, 'move'>, { left: string | number; top: string | number; cursor: string }> = {
  nw: { left: 0,      top: 0,      cursor: 'nwse-resize' },
  n:  { left: '50%',  top: 0,      cursor: 'ns-resize'   },
  ne: { left: '100%', top: 0,      cursor: 'nesw-resize' },
  w:  { left: 0,      top: '50%',  cursor: 'ew-resize'   },
  e:  { left: '100%', top: '50%',  cursor: 'ew-resize'   },
  sw: { left: 0,      top: '100%', cursor: 'nesw-resize' },
  s:  { left: '50%',  top: '100%', cursor: 'ns-resize'   },
  se: { left: '100%', top: '100%', cursor: 'nwse-resize' },
}

function BboxEditor({
  bbox, natW, natH, imgRef, onDone,
}: {
  bbox: [number, number, number, number]
  natW: number
  natH: number
  imgRef: React.RefObject<HTMLImageElement | null>
  onDone: (newBbox: [number, number, number, number]) => void
}) {
  const [live, setLive] = useState<[number, number, number, number]>(bbox)
  const liveRef   = useRef(bbox)
  const drag      = useRef<{ handle: Handle; sx: number; sy: number; startBbox: [number, number, number, number] } | null>(null)
  const onDoneRef = useRef(onDone)
  useEffect(() => { onDoneRef.current = onDone }, [onDone])

  useEffect(() => { setLive(bbox); liveRef.current = bbox }, [bbox])

  const getScale = useCallback((): [number, number] => {
    const img = imgRef.current
    if (!img || natW === 0 || natH === 0) return [1, 1]
    const r = img.getBoundingClientRect()
    return [natW / r.width, natH / r.height]
  }, [imgRef, natW, natH])

  const startDrag = (e: React.MouseEvent, handle: Handle) => {
    e.preventDefault(); e.stopPropagation()
    drag.current = { handle, sx: e.clientX, sy: e.clientY, startBbox: liveRef.current }
  }

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!drag.current) return
      const { handle, sx, sy, startBbox } = drag.current
      const [scx, scy] = getScale()
      const dx = (e.clientX - sx) * scx
      const dy = (e.clientY - sy) * scy
      let [x1, y1, x2, y2] = startBbox
      if (handle === 'move') {
        const w = x2 - x1, h = y2 - y1
        x1 = Math.max(0, Math.min(x1 + dx, natW - w)); y1 = Math.max(0, Math.min(y1 + dy, natH - h))
        x2 = x1 + w; y2 = y1 + h
      } else {
        if (handle.includes('w')) x1 = Math.max(0, Math.min(startBbox[0] + dx, x2 - 4))
        if (handle.includes('e')) x2 = Math.min(natW, Math.max(startBbox[2] + dx, x1 + 4))
        if (handle.includes('n')) y1 = Math.max(0, Math.min(startBbox[1] + dy, y2 - 4))
        if (handle.includes('s')) y2 = Math.min(natH, Math.max(startBbox[3] + dy, y1 + 4))
      }
      const nb: [number, number, number, number] = [Math.round(x1), Math.round(y1), Math.round(x2), Math.round(y2)]
      liveRef.current = nb; setLive(nb)
    }
    const onUp = () => {
      if (!drag.current) return
      drag.current = null; onDoneRef.current(liveRef.current)
    }
    window.addEventListener('mousemove', onMove); window.addEventListener('mouseup', onUp)
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp) }
  }, [getScale, natW, natH])

  const [x1, y1, x2, y2] = live
  return (
    <div onMouseDown={e => startDrag(e, 'move')} style={{
      position: 'absolute',
      left: `${(x1 / natW) * 100}%`, top: `${(y1 / natH) * 100}%`,
      width: `${((x2 - x1) / natW) * 100}%`, height: `${((y2 - y1) / natH) * 100}%`,
      border: '2px solid rgba(245,158,11,1)', boxSizing: 'border-box',
      cursor: 'move', background: 'rgba(245,158,11,0.1)', zIndex: 20,
    }}>
      {(Object.keys(HANDLE_POS) as Exclude<Handle, 'move'>[]).map(h => (
        <div key={h} onMouseDown={e => startDrag(e, h)} style={{
          position: 'absolute', left: HANDLE_POS[h].left, top: HANDLE_POS[h].top,
          transform: 'translate(-50%, -50%)', width: 10, height: 10,
          background: 'white', border: '2px solid rgba(245,158,11,1)',
          borderRadius: 2, cursor: HANDLE_POS[h].cursor, zIndex: 21,
        }} />
      ))}
    </div>
  )
}

// ── DrawLayer ─────────────────────────────────────────────────────────────────

/**
 * Transparent overlay that lets the user drag a new bounding box on the image.
 * Renders a dashed blue preview rect during drag; calls onDone with image-pixel
 * coordinates on mouseup (only if the drawn rect is larger than 3×3 px).
 */
function DrawLayer({
  imgRef, onDone,
}: {
  imgRef: React.RefObject<HTMLImageElement | null>
  onDone: (bbox: [number, number, number, number]) => void
}) {
  const [liveRect, setLiveRect] = useState<[number, number, number, number] | null>(null)
  const startRef = useRef<[number, number] | null>(null)
  const onDoneRef = useRef(onDone)
  useEffect(() => { onDoneRef.current = onDone }, [onDone])

  // Read current image natural dimensions + position at event time (always fresh)
  const toImgPt = (clientX: number, clientY: number): [number, number] => {
    const img = imgRef.current
    if (!img) return [0, 0]
    const r = img.getBoundingClientRect()
    const nW = img.naturalWidth, nH = img.naturalHeight
    return [
      Math.round(Math.max(0, Math.min((clientX - r.left) * nW / r.width, nW))),
      Math.round(Math.max(0, Math.min((clientY - r.top)  * nH / r.height, nH))),
    ]
  }

  const onMouseDown = (e: React.MouseEvent) => {
    e.preventDefault()
    startRef.current = toImgPt(e.clientX, e.clientY)
  }

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!startRef.current) return
      const [x0, y0] = startRef.current
      const [x1, y1] = toImgPt(e.clientX, e.clientY)
      setLiveRect([Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1)])
    }
    const onUp = (e: MouseEvent) => {
      if (!startRef.current) return
      const [x0, y0] = startRef.current
      startRef.current = null
      setLiveRect(null)
      const [x1, y1] = toImgPt(e.clientX, e.clientY)
      const bbox: [number, number, number, number] = [
        Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1),
      ]
      if (bbox[2] - bbox[0] > 3 && bbox[3] - bbox[1] > 3) {
        onDoneRef.current(bbox)
      }
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp) }
  }, [])  // no deps — reads from refs and DOM directly

  const img = imgRef.current
  const natW = img?.naturalWidth ?? 1
  const natH = img?.naturalHeight ?? 1

  return (
    <>
      <div onMouseDown={onMouseDown} style={{
        position: 'absolute', inset: 0, cursor: 'crosshair', zIndex: 25,
      }} />
      {liveRect && natW > 0 && (
        <div style={{
          position: 'absolute',
          left:   `${(liveRect[0] / natW) * 100}%`,
          top:    `${(liveRect[1] / natH) * 100}%`,
          width:  `${((liveRect[2] - liveRect[0]) / natW) * 100}%`,
          height: `${((liveRect[3] - liveRect[1]) / natH) * 100}%`,
          border: '2px dashed #3b82f6',
          background: 'rgba(59,130,246,0.12)',
          boxSizing: 'border-box',
          zIndex: 26,
          pointerEvents: 'none',
        }} />
      )}
    </>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function CharCrop({ imageUrl, bbox }: { imageUrl: string; bbox: [number, number, number, number] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const img = new window.Image()
    img.onload = () => {
      const canvas = canvasRef.current
      if (!canvas) return
      const [x1, y1, x2, y2] = bbox
      const cw = Math.max(1, x2 - x1), ch = Math.max(1, y2 - y1)
      const scale = Math.min(5, Math.min(200 / cw, 160 / ch))
      canvas.width = Math.ceil(cw * scale); canvas.height = Math.ceil(ch * scale)
      const ctx = canvas.getContext('2d')!
      ctx.imageSmoothingEnabled = false
      ctx.drawImage(img, x1, y1, cw, ch, 0, 0, canvas.width, canvas.height)
    }
    img.src = imageUrl
  }, [imageUrl, bbox])

  return (
    <canvas ref={canvasRef} className="border-2 border-amber-400 rounded bg-white"
      style={{ imageRendering: 'pixelated' }} />
  )
}

function ProgressBar({ confirmed, total }: { confirmed: number; total: number }) {
  const pct = total > 0 ? Math.round((confirmed / total) * 100) : 0
  return (
    <div className="flex items-center gap-2 text-sm text-gray-600">
      <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
        <div className="h-full bg-green-500 transition-all" style={{ width: `${pct}%` }} />
      </div>
      <span className="tabular-nums whitespace-nowrap">{confirmed} / {total}</span>
    </div>
  )
}

function LineImage({
  src, chars, currentCharIdx, showBoxes, onNaturalSize,
  editingCharIdx, onBboxChange,
  drawMode, onDrawComplete,
}: {
  src: string
  chars: CharBox[]
  currentCharIdx: number | null
  showBoxes: boolean
  onNaturalSize: (w: number, h: number) => void
  editingCharIdx?: number | null
  onBboxChange?: (charIdx: number, newBbox: [number, number, number, number]) => void
  drawMode?: boolean
  onDrawComplete?: (bbox: [number, number, number, number]) => void
}) {
  const [natW, setNatW] = useState(0)
  const [natH, setNatH] = useState(0)
  const imgRef = useRef<HTMLImageElement | null>(null)

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-2 overflow-hidden">
      <div style={{ position: 'relative', display: 'inline-block', width: '100%' }}>
        <img
          ref={imgRef}
          src={src}
          alt="Line"
          style={{ width: '100%', display: 'block', imageRendering: 'pixelated' }}
          onLoad={e => {
            const img = e.currentTarget
            setNatW(img.naturalWidth); setNatH(img.naturalHeight)
            onNaturalSize(img.naturalWidth, img.naturalHeight)
          }}
        />
        {showBoxes && natW > 0 && chars.map((c, i) => {
          if (i === editingCharIdx) return null
          const [x1, y1, x2, y2] = c.bbox
          const isCurrent = currentCharIdx === i
          const isLabeled = currentCharIdx !== null && i < currentCharIdx
          return (
            <div key={c.id} title={c.ocr_char ?? '?'} style={{
              position: 'absolute',
              left:   `${(x1 / natW) * 100}%`,
              top:    `${(y1 / natH) * 100}%`,
              width:  `${((x2 - x1) / natW) * 100}%`,
              height: `${((y2 - y1) / natH) * 100}%`,
              border: isCurrent
                ? '2px solid rgba(245,158,11,1)'
                : isLabeled
                  ? '1px solid rgba(34,197,94,0.6)'
                  : '1px solid rgba(251,146,60,0.5)',
              boxSizing: 'border-box',
              pointerEvents: 'none',
              background: isCurrent ? 'rgba(245,158,11,0.1)' : 'transparent',
            }} />
          )
        })}
        {editingCharIdx != null && editingCharIdx < chars.length && natW > 0 && showBoxes && (
          <BboxEditor
            bbox={chars[editingCharIdx].bbox}
            natW={natW} natH={natH} imgRef={imgRef}
            onDone={newBbox => onBboxChange?.(editingCharIdx, newBbox)}
          />
        )}
        {drawMode && onDrawComplete && (
          <DrawLayer imgRef={imgRef} onDone={onDrawComplete} />
        )}
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function LabelingView() {
  const [hand, setHand]         = useState<'a' | 'b'>('b')
  const [mode, setMode]         = useState<LabelMode>('line')
  const [samples, setSamples]   = useState<Sample[]>([])
  const [index, setIndex]       = useState(0)
  const [current, setCurrent]   = useState<Sample | null>(null)
  const [stats, setStats]       = useState<Stats>({})
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState<string | null>(null)
  const [showBoxes, setShowBoxes] = useState(true)

  const [lineText, setLineText]   = useState('')
  const pendingCursorRef          = useRef<number | null>(null)
  const textareaRef               = useRef<HTMLTextAreaElement>(null)

  const [charIdx, setCharIdx]         = useState(0)
  const [charLabels, setCharLabels]   = useState<(string | null)[]>([])
  const [detecting, setDetecting]     = useState(false)
  const [bboxEditMode, setBboxEditMode] = useState(false)
  const [drawMode, setDrawMode]         = useState(false)

  // Mutually exclusive: enabling draw turns off edit, and vice versa
  const toggleDraw = useCallback(() => {
    setDrawMode(v => { if (!v) setBboxEditMode(false); return !v })
  }, [])
  const toggleEdit = useCallback(() => {
    setBboxEditMode(v => { if (!v) setDrawMode(false); return !v })
  }, [])

  // Reset both modes when char changes
  useEffect(() => { setBboxEditMode(false); setDrawMode(false) }, [charIdx])

  useEffect(() => {
    setLoading(true); setError(null)
    Promise.all([fetchSamples(hand), fetchStats()])
      .then(([list, s]) => { setSamples(list); setStats(s); setIndex(0) })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [hand])

  useEffect(() => {
    const s = samples[index]
    if (!s) { setCurrent(null); return }
    fetchSample(s.id)
      .then(full => {
        setCurrent(full)
        setLineText(full.ground_truth ?? full.ocr_guess ?? '')
        setCharIdx(0)
        setCharLabels(new Array(full.chars.length).fill(null))
      })
      .catch(e => setError(String(e)))
  }, [samples, index])

  useEffect(() => {
    const cur = pendingCursorRef.current
    if (cur !== null && textareaRef.current) {
      textareaRef.current.selectionStart = cur
      textareaRef.current.selectionEnd   = cur
      pendingCursorRef.current = null
    }
  })

  const advance = useCallback(() => {
    setSamples(prev => prev.filter((_, i) => i !== index))
    setIndex(i => Math.min(i, samples.length - 2))
    setCharIdx(0); setCharLabels([])
  }, [index, samples.length])

  const refreshStats = useCallback(() => fetchStats().then(setStats).catch(() => {}), [])

  const insertChar = useCallback((value: string) => {
    const el = textareaRef.current
    const start = el?.selectionStart ?? lineText.length
    const end   = el?.selectionEnd   ?? lineText.length
    const newText = lineText.slice(0, start) + value + lineText.slice(end)
    pendingCursorRef.current = start + value.length
    setLineText(newText); el?.focus()
  }, [lineText])

  const deleteChar = useCallback(() => {
    const el = textareaRef.current
    const start = el?.selectionStart ?? lineText.length
    const end   = el?.selectionEnd   ?? lineText.length
    let newText: string, newCursor: number
    if (start !== end) {
      newText = lineText.slice(0, start) + lineText.slice(end); newCursor = start
    } else if (start > 0) {
      const cp = [...lineText.slice(0, start)]; cp.pop()
      newText = cp.join('') + lineText.slice(start); newCursor = cp.join('').length
    } else { return }
    pendingCursorRef.current = newCursor
    setLineText(newText); el?.focus()
  }, [lineText])

  const confirmLine = useCallback(async () => {
    if (!current) return
    await postLabel(current.id, lineText)
    await refreshStats(); advance()
  }, [current, lineText, advance, refreshStats])

  const skipLine = useCallback(async () => {
    if (!current) return
    await postSkip(current.id); advance()
  }, [current, advance])

  const labelChar = useCallback(async (value: string) => {
    if (!current || charIdx >= current.chars.length) return
    await postCharLabel(current.chars[charIdx].id, value)
    setCharLabels(prev => { const n = [...prev]; n[charIdx] = value; return n })
    setCharIdx(ci => ci + 1)
  }, [current, charIdx])

  const skipChar = useCallback(() => {
    setCharLabels(prev => { const n = [...prev]; n[charIdx] = null; return n })
    setCharIdx(ci => ci + 1)
  }, [charIdx])

  const backChar = useCallback(() => {
    if (charIdx > 0) setCharIdx(ci => ci - 1)
  }, [charIdx])

  const confirmFromChars = useCallback(async () => {
    if (!current) return
    await postLabel(current.id, charLabels.filter(Boolean).join(''))
    await refreshStats(); advance()
  }, [current, charLabels, advance, refreshStats])

  const redetectChars = useCallback(async () => {
    if (!current) return
    setDetecting(true)
    try {
      await postDetectChars(current.id)
      const fresh = await fetchSample(current.id)
      setCurrent(fresh); setCharIdx(0)
      setCharLabels(new Array(fresh.chars.length).fill(null))
    } catch (e) { setError(String(e)) }
    finally { setDetecting(false) }
  }, [current])

  const handleBboxChange = useCallback(async (editIdx: number, newBbox: [number, number, number, number]) => {
    if (!current) return
    const charId = current.chars[editIdx].id
    setCurrent(prev => {
      if (!prev) return prev
      return { ...prev, chars: prev.chars.map((c, i) => i === editIdx ? { ...c, bbox: newBbox } : c) }
    })
    await patchBbox(charId, newBbox).catch(e => setError(String(e)))
  }, [current])

  // ── Draw new bbox ──────────────────────────────────────────────────────────
  const handleDrawComplete = useCallback(async (bbox: [number, number, number, number]) => {
    if (!current) return
    setDrawMode(false)
    try {
      const newChar: CharBox = await postAddChar(current.id, bbox)
      // Insert sorted by x1 and navigate to the new char
      setCurrent(prev => {
        if (!prev) return prev
        const chars = [...prev.chars, newChar].sort((a, b) => a.bbox[0] - b.bbox[0])
        return { ...prev, chars }
      })
      // Position charIdx at the new char
      const insertPos = current.chars.filter(c => c.bbox[0] < bbox[0]).length
      setCharIdx(insertPos)
      setCharLabels(prev => {
        const n = [...prev]
        n.splice(insertPos, 0, null)
        return n
      })
    } catch (e) { setError(String(e)) }
  }, [current])

  // ── Delete current bbox ────────────────────────────────────────────────────
  const handleDeleteChar = useCallback(async () => {
    if (!current || charIdx >= current.chars.length) return
    const charId = current.chars[charIdx].id
    try {
      await deleteCharApi(charId)
      setCurrent(prev => {
        if (!prev) return prev
        return { ...prev, chars: prev.chars.filter(c => c.id !== charId) }
      })
      setCharLabels(prev => prev.filter((_, i) => i !== charIdx))
      // Stay at same index (now pointing to the next char, or the last one)
      setCharIdx(ci => Math.min(ci, current.chars.length - 2))
    } catch (e) { setError(String(e)) }
  }, [current, charIdx])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target === textareaRef.current) return
      if (mode === 'line') {
        if (e.key === 'Enter') { e.preventDefault(); confirmLine() }
        if (e.key === 'Tab')   { e.preventDefault(); skipLine() }
      }
      if (e.key === 'ArrowRight') setIndex(i => Math.min(i + 1, samples.length - 1))
      if (e.key === 'ArrowLeft')  setIndex(i => Math.max(i - 1, 0))
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [mode, confirmLine, skipLine, samples.length])

  const handStats       = stats[hand]
  const allCharsLabeled = current ? charIdx >= current.chars.length : false

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col">

      <header className="bg-white border-b border-gray-200 px-4 py-3 flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold text-gray-800 font-serif">αινίγματα — Labeling</h1>

        <div className="flex items-center gap-1 text-sm">
          <span className="text-gray-400 mr-1">Hand:</span>
          {(['b', 'a'] as const).map(h => (
            <button key={h} onClick={() => setHand(h)}
              className={`px-3 py-1 rounded border text-sm font-medium transition-colors ${
                hand === h ? 'bg-amber-600 text-white border-amber-600'
                           : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'}`}>
              {h === 'a' ? 'A (ff. 1–40)' : 'B (ff. 41+)'}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1 text-sm">
          <span className="text-gray-400 mr-1">Mode:</span>
          {(['line', 'char'] as const).map(m => (
            <button key={m} onClick={() => setMode(m)}
              className={`px-3 py-1 rounded border text-sm font-medium transition-colors ${
                mode === m ? 'bg-blue-600 text-white border-blue-600'
                           : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'}`}>
              {m === 'line' ? '≡ Line' : '∣ Char'}
            </button>
          ))}
        </div>

        <label className="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer">
          <input type="checkbox" checked={showBoxes}
            onChange={e => setShowBoxes(e.target.checked)} className="accent-amber-500" />
          Boxes
        </label>

        <div className="flex-1 min-w-[160px] max-w-xs">
          {handStats
            ? <ProgressBar confirmed={handStats.confirmed} total={handStats.total} />
            : <span className="text-xs text-gray-400">No data</span>}
        </div>
      </header>

      <main className="flex-1 max-w-4xl mx-auto w-full px-4 py-5 space-y-4">

        {error && (
          <div className="bg-red-50 border border-red-300 text-red-700 rounded p-3 text-sm">
            {error}
            <button className="ml-3 underline text-xs" onClick={() => setError(null)}>dismiss</button>
          </div>
        )}

        {loading && <p className="text-center text-gray-400 py-12">Loading…</p>}

        {!loading && samples.length === 0 && !error && (
          <div className="text-center py-16 text-gray-500">
            <p className="text-2xl mb-2">✓</p>
            <p>No pending samples for Hand {hand.toUpperCase()}.</p>
            <p className="text-sm mt-2">
              Run:{' '}
              <code className="font-mono text-xs bg-gray-100 px-2 py-0.5 rounded">
                python -m src.training.extractor --manuscript vat.gr.1209 --folio 41
              </code>
            </p>
          </div>
        )}

        {!loading && current && (
          <>
            <div className="flex items-center justify-between text-sm text-gray-500">
              <button onClick={() => setIndex(i => Math.max(i - 1, 0))} disabled={index === 0}
                className="px-3 py-1 rounded border border-gray-300 hover:bg-gray-50 disabled:opacity-30">
                ← Prev
              </button>
              <span>
                Folio <strong>{current.folio}</strong> · Col {current.column_index ?? '?'} ·
                {' '}Line {index + 1}/{samples.length}
              </span>
              <button onClick={() => setIndex(i => Math.min(i + 1, samples.length - 1))}
                disabled={index >= samples.length - 1}
                className="px-3 py-1 rounded border border-gray-300 hover:bg-gray-50 disabled:opacity-30">
                Next →
              </button>
            </div>

            <LineImage
              src={current.image_url}
              chars={current.chars}
              currentCharIdx={mode === 'char' ? charIdx : null}
              showBoxes={showBoxes}
              onNaturalSize={() => {}}
              editingCharIdx={mode === 'char' && bboxEditMode && !drawMode ? charIdx : null}
              onBboxChange={handleBboxChange}
              drawMode={mode === 'char' && drawMode}
              onDrawComplete={handleDrawComplete}
            />

            {/* ════════════ LINE MODE ════════════════════════════════ */}
            {mode === 'line' && (
              <>
                {current.ocr_guess && (
                  <p className="text-xs text-gray-400 font-mono px-1">
                    OCR: <span className="text-gray-600 font-serif text-sm">{current.ocr_guess}</span>
                  </p>
                )}
                <textarea
                  ref={textareaRef}
                  value={lineText}
                  onChange={e => setLineText(e.target.value)}
                  rows={2} dir="ltr" spellCheck={false}
                  placeholder="Type or use the keyboard…"
                  className="w-full rounded-lg border px-3 py-2 font-serif text-xl text-gray-900 resize-none focus:outline-none focus:ring-2 focus:ring-amber-400 border-gray-300 bg-white leading-relaxed"
                />
                <VirtualKeyboard onKey={insertChar} onDelete={deleteChar} />
                <div className="flex gap-2 justify-end">
                  <button onClick={skipLine}
                    className="px-4 py-2 rounded border border-gray-300 text-gray-600 hover:bg-gray-50 text-sm">
                    Skip
                  </button>
                  <button onClick={confirmLine} disabled={lineText.trim() === ''}
                    className="px-5 py-2 rounded text-sm font-medium bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-40">
                    ✓ Confirm  <span className="text-xs opacity-60">(Enter)</span>
                  </button>
                </div>
                <p className="text-xs text-gray-400 text-right -mt-1">Tab = skip · ← → = navigate</p>
              </>
            )}

            {/* ════════════ CHAR MODE ════════════════════════════════ */}
            {mode === 'char' && (
              <>
                {current.chars.length === 0 ? (
                  <div className="text-center py-4 text-gray-500 text-sm space-y-2">
                    <p>No character boxes detected.</p>
                    <div className="flex gap-2 justify-center">
                      <button onClick={redetectChars} disabled={detecting}
                        className="px-4 py-2 rounded bg-purple-600 text-white text-sm hover:bg-purple-700 disabled:opacity-40">
                        {detecting ? 'Detecting…' : '⟳ Run detection'}
                      </button>
                      <button onClick={toggleDraw}
                        className={`px-4 py-2 rounded text-sm border ${
                          drawMode ? 'bg-blue-600 text-white border-blue-600'
                                   : 'border-blue-300 text-blue-700 hover:bg-blue-50'}`}>
                        + Draw box
                      </button>
                    </div>
                    {drawMode && (
                      <p className="text-xs text-blue-600">Click and drag on the image above to draw a bounding box</p>
                    )}
                  </div>
                ) : allCharsLabeled ? (
                  <div className="space-y-3">
                    <p className="text-sm text-green-700 font-medium">
                      ✓ All {current.chars.length} characters labeled.
                    </p>
                    <div className="font-serif text-2xl tracking-widest text-gray-900 bg-white rounded border px-4 py-3">
                      {charLabels.map((l, i) => (
                        <span key={i} className={l ? '' : 'text-red-300'} title={l ?? 'skipped'}>{l ?? '?'}</span>
                      ))}
                    </div>
                    <div className="flex gap-2 justify-end">
                      <button onClick={backChar}
                        className="px-3 py-2 rounded border border-gray-300 text-gray-600 hover:bg-gray-50 text-sm">
                        ← Fix last
                      </button>
                      <button onClick={skipLine}
                        className="px-4 py-2 rounded border border-gray-300 text-gray-600 hover:bg-gray-50 text-sm">
                        Skip line
                      </button>
                      <button onClick={confirmFromChars}
                        className="px-5 py-2 rounded text-sm font-medium bg-amber-600 text-white hover:bg-amber-700">
                        ✓ Confirm line
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="flex items-start gap-4">
                      <div className="flex flex-col items-center gap-2">
                        <CharCrop
                          imageUrl={current.image_url}
                          bbox={current.chars[charIdx].bbox}
                        />
                        <span className="text-xs text-gray-400">
                          char {charIdx + 1} of {current.chars.length}
                        </span>
                      </div>

                      <div className="flex-1">
                        <p className="text-xs text-gray-400 mb-1">Labeled so far:</p>
                        <div className="font-serif text-xl tracking-wider min-h-[2rem] bg-white rounded border px-2 py-1">
                          {charLabels.slice(0, charIdx).map((l, i) => (
                            <span key={i} className={l ? 'text-gray-900' : 'text-red-300'}>{l ?? '?'}</span>
                          ))}
                          <span className="animate-pulse text-amber-500">|</span>
                        </div>

                        {/* Controls */}
                        <div className="flex flex-wrap gap-2 mt-2">
                          <button onClick={backChar} disabled={charIdx === 0}
                            className="px-3 py-1 rounded border border-gray-300 text-gray-600 text-xs hover:bg-gray-50 disabled:opacity-30">
                            ← Back
                          </button>
                          <button onClick={skipChar}
                            className="px-3 py-1 rounded border border-gray-300 text-gray-600 text-xs hover:bg-gray-50">
                            Skip
                          </button>
                          <button onClick={redetectChars} disabled={detecting}
                            className="px-3 py-1 rounded border border-purple-300 text-purple-700 text-xs hover:bg-purple-50 disabled:opacity-40">
                            {detecting ? '…' : '⟳ Re-detect'}
                          </button>
                          <button onClick={toggleEdit}
                            title="Drag handles to resize/move the current box"
                            className={`px-3 py-1 rounded border text-xs transition-colors ${
                              bboxEditMode ? 'bg-blue-600 text-white border-blue-600'
                                           : 'border-blue-300 text-blue-700 hover:bg-blue-50'}`}>
                            ✏ Edit box
                          </button>
                          <button onClick={toggleDraw}
                            title="Draw a new bounding box on the image"
                            className={`px-3 py-1 rounded border text-xs transition-colors ${
                              drawMode ? 'bg-green-600 text-white border-green-600'
                                       : 'border-green-300 text-green-700 hover:bg-green-50'}`}>
                            + Draw
                          </button>
                          <button onClick={handleDeleteChar}
                            title="Delete this bounding box"
                            className="px-3 py-1 rounded border border-red-300 text-red-600 text-xs hover:bg-red-50">
                            ✕ Delete
                          </button>
                        </div>

                        {bboxEditMode && !drawMode && (
                          <p className="text-xs text-blue-600 mt-1.5 leading-snug">
                            Drag corners/edges to resize · drag center to move · saves automatically
                          </p>
                        )}
                        {drawMode && (
                          <p className="text-xs text-green-700 mt-1.5 leading-snug">
                            Click and drag on the image above to draw a new box
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="relative">
                      <div className="absolute -top-2 left-2 bg-blue-600 text-white text-xs px-2 py-0.5 rounded">
                        click a key to label this character
                      </div>
                      <VirtualKeyboard onKey={labelChar} onDelete={backChar} charMode />
                    </div>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </main>
    </div>
  )
}
