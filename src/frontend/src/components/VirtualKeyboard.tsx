interface VirtualKeyboardProps {
  onKey: (value: string) => void
  onDelete: () => void
  /** In char mode, highlight only one key at a time on physical keypress */
  charMode?: boolean
}

// ── 1. Standard Greek alphabet (uppercase) ───────────────────────────────────
// All 24 letters of the classical alphabet.  Ζ (zeta) is in row 1 pos 6.
const GREEK_ROW_1 = ['Α','Β','Γ','Δ','Ε','Ζ','Η','Θ','Ι','Κ','Λ','Μ']
const GREEK_ROW_2 = ['Ν','Ξ','Ο','Π','Ρ','Σ','Τ','Υ','Φ','Χ','Ψ','Ω']

// ── 2. Sigma variants + primary punctuation + controls ───────────────────────
// Ϲ (U+03F9) = lunate sigma — the C-shaped form actually used in the Vaticanus.
// Standard Σ is in row 2 for manuscripts that use the three-bar form.
const SPECIAL_ROW = [
  { label: 'Ϲ', value: 'Ϲ', title: 'Lunate sigma Ϲ (U+03F9) — the form in the Vaticanus' },
  { label: 'ϲ', value: 'ϲ', title: 'Lunate sigma ϲ (U+03F2) — lowercase form' },
  { label: 'ς', value: 'ς', title: 'Final sigma ς (U+03C2) — end-of-word form' },
  { label: '·', value: '\u0387', title: 'Ano teleia · (U+0387) — Greek high dot, primary clause separator' },
  { label: ';', value: '\u037E', title: 'Greek question mark ; (U+037E) — looks like semicolon' },
  { label: ',', value: ',',  title: 'Comma' },
  { label: '÷', value: '÷',  title: 'Dicolon ÷ — major section break' },
  { label: '¶', value: '¶',  title: 'Paragraph mark' },
  { label: '>', value: '>',  title: 'Diple > — quotation / variant marker' },
  { label: '—', value: '—',  title: 'Em dash — lacuna (missing text)' },
]

// ── 3. Archaic letters used as numerals ──────────────────────────────────────
// These appear frequently in the Vaticanus as chapter/page numbers.
//   Ϛ (U+03DA) stigma  = 6    ← looks like a reversed ζ or ς variant
//   Ϟ (U+03DE) koppa   = 90   ← looks like a Q with a tail / angular hook
//   Ϡ (U+03E0) sampi   = 900  ← looks like a T-bar or π variant
//   Ϝ (U+03DC) digamma = 6 in some archaic traditions (also the letter waw)
//
// The Greek numeral sign ʹ (U+0374) follows the letter: Αʹ = 1, Βʹ = 2, etc.
// The lower numeral sign ͵ (U+0375) precedes thousands: ͵Α = 1000.
const ARCHAIC_ROW = [
  { label: 'Ϛ', value: 'Ϛ', title: 'Stigma Ϛ (U+03DA) — numeral 6; looks like a stylised ζ' },
  { label: 'ϛ', value: 'ϛ', title: 'Stigma ϛ (U+03DB) — lowercase; most common form in NT manuscripts' },
  { label: 'Ϟ', value: 'Ϟ', title: 'Koppa Ϟ (U+03DE) — numeral 90; angular hook shape' },
  { label: 'ϟ', value: 'ϟ', title: 'Koppa ϟ (U+03DF) — lowercase' },
  { label: 'Ϡ', value: 'Ϡ', title: 'Sampi Ϡ (U+03E0) — numeral 900; rare in NT, common in older texts' },
  { label: 'ϡ', value: 'ϡ', title: 'Sampi ϡ (U+03E1) — lowercase' },
  { label: 'Ϝ', value: 'Ϝ', title: 'Digamma Ϝ (U+03DC) — archaic; numeral 6 in some Doric traditions' },
  { label: 'ϝ', value: 'ϝ', title: 'Digamma ϝ (U+03DD) — lowercase' },
  { label: 'ʹ', value: '\u0374', title: 'Greek numeral sign ʹ (U+0374) — follows the letter: Αʹ = 1' },
  { label: '͵', value: '\u0375', title: 'Greek lower numeral sign ͵ (U+0375) — precedes thousands: ͵Α = 1000' },
]

// ── 4. Nomina sacra ───────────────────────────────────────────────────────────
// Sacred-name abbreviations with a horizontal overline.
// Unicode: combining overline U+0305 placed after the final letter of the abbreviation.
const NOMINA_SACRA = [
  { label: 'ΙΣ̄',  value: 'ΙΣ\u0305',   title: 'Ἰησοῦς — Jesus' },
  { label: 'ΧΣ̄',  value: 'ΧΣ\u0305',   title: 'Χριστός — Christ' },
  { label: 'ΘΣ̄',  value: 'ΘΣ\u0305',   title: 'θεός — God' },
  { label: 'ΚΣ̄',  value: 'ΚΣ\u0305',   title: 'κύριος — Lord' },
  { label: 'ΠΝᾹ', value: 'ΠΝΑ\u0305',  title: 'πνεῦμα — Spirit' },
  { label: 'ΠΡΣ̄', value: 'ΠΡΣ\u0305',  title: 'πατήρ — Father' },
  { label: 'ΑΝΣ̄', value: 'ΑΝΣ\u0305',  title: 'ἄνθρωπος — human being' },
  { label: 'ΟΝΣ̄', value: 'ΟΝΣ\u0305',  title: 'οὐρανός — heaven' },
  { label: 'ΔΑΔ̄', value: 'ΔΑΔ\u0305',  title: 'Δαυίδ — David' },
  { label: 'ΙΗΛ̄', value: 'ΙΗΛ\u0305',  title: 'Ἰσραήλ — Israel' },
  { label: 'ΜΡ̄',  value: 'ΜΡ\u0305',   title: 'μήτηρ — mother (Mary)' },
  { label: 'ΥΣ̄',  value: 'ΥΣ\u0305',   title: 'υἱός — son' },
]

// ── 5. Lowercase Greek alphabet (collapsed — for minuscule manuscripts) ───────
const LOWER_ROW_1 = ['α','β','γ','δ','ε','ζ','η','θ','ι','κ','λ','μ']
const LOWER_ROW_2 = ['ν','ξ','ο','π','ρ','σ','τ','υ','φ','χ','ψ','ω']

// ── 6. Combining diacritical marks (corrector hands) ─────────────────────────
// These are combining characters and attach to the preceding letter.
const CORRECTOR_MARKS = [
  { label: '◌́',  value: '\u0301', title: 'Acute accent ◌́' },
  { label: '◌̀',  value: '\u0300', title: 'Grave accent ◌̀' },
  { label: '◌͂',  value: '\u0342', title: 'Perispomeni (circumflex) ◌͂' },
  { label: '◌̓',  value: '\u0313', title: 'Smooth breathing (spiritus lenis) ◌̓' },
  { label: '◌̔',  value: '\u0314', title: 'Rough breathing (spiritus asper) ◌̔' },
  { label: '◌ͅ',  value: '\u0345', title: 'Iota subscript ◌ͅ' },
  { label: '◌̈',  value: '\u0308', title: 'Diaeresis ◌̈' },
  { label: '◌̄',  value: '\u0305', title: 'Combining overline ◌̄ (numeral / nomen sacrum bar)' },
  { label: '◌̃',  value: '\u0303', title: 'Combining tilde ◌̃' },
  { label: '◌̣',  value: '\u0323', title: 'Combining dot below ◌̣ (uncertain reading)' },
]

// ── Shared button styles ──────────────────────────────────────────────────────

const btnBase =
  'min-w-[2.25rem] h-9 px-1.5 rounded border border-gray-300 bg-white ' +
  'text-gray-900 font-serif text-lg leading-none select-none ' +
  'hover:bg-amber-50 hover:border-amber-400 active:bg-amber-100 ' +
  'transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-amber-400'

const btnArchaic =
  'min-w-[2.25rem] h-9 px-1.5 rounded border border-purple-300 bg-purple-50 ' +
  'text-purple-900 font-serif text-lg leading-none select-none ' +
  'hover:bg-purple-100 active:bg-purple-200 ' +
  'transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-purple-400'

const btnNomen =
  'px-2 h-9 rounded border border-amber-400 bg-amber-50 ' +
  'text-amber-900 font-serif text-base leading-none select-none ' +
  'hover:bg-amber-100 active:bg-amber-200 ' +
  'transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-amber-500'

const btnDiacritic =
  'min-w-[2.25rem] h-9 px-1.5 rounded border border-blue-300 bg-blue-50 ' +
  'text-blue-900 font-serif text-lg leading-none select-none ' +
  'hover:bg-blue-100 active:bg-blue-200 ' +
  'transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-400'

const btnSpecial =
  'px-2 h-9 rounded border border-gray-400 bg-gray-100 ' +
  'text-gray-700 text-sm leading-none select-none ' +
  'hover:bg-gray-200 active:bg-gray-300 ' +
  'transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-gray-400'

const btnLower =
  'min-w-[2.25rem] h-9 px-1.5 rounded border border-gray-300 bg-white ' +
  'text-gray-500 font-serif text-base leading-none select-none ' +
  'hover:bg-gray-50 hover:border-gray-400 active:bg-gray-100 ' +
  'transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-gray-400'

// ─────────────────────────────────────────────────────────────────────────────

export default function VirtualKeyboard({ onKey, onDelete }: VirtualKeyboardProps) {
  return (
    <div className="space-y-2 p-3 bg-gray-50 rounded-lg border border-gray-200 select-none">

      {/* ── 1. Uppercase alphabet ───────────────────────────────── */}
      <div className="flex flex-wrap gap-1">
        {GREEK_ROW_1.map(ch => (
          <button key={ch} className={btnBase} title={ch} onClick={() => onKey(ch)}>
            {ch}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap gap-1">
        {GREEK_ROW_2.map(ch => (
          <button key={ch} className={btnBase} title={ch} onClick={() => onKey(ch)}>
            {ch}
          </button>
        ))}
      </div>

      {/* ── 2. Sigma variants + punctuation + controls ──────────── */}
      <div className="flex flex-wrap items-center gap-1">
        {SPECIAL_ROW.map(k => (
          <button key={k.label} className={btnBase} title={k.title} onClick={() => onKey(k.value)}>
            {k.label}
          </button>
        ))}
        <button className={`${btnSpecial} px-4`} title="Space" onClick={() => onKey(' ')}>
          SPACE
        </button>
        <button className={`${btnSpecial} px-3 text-base`} title="Backspace" onClick={onDelete}>
          ⌫
        </button>
      </div>

      {/* ── 3. Archaic numeral letters ──────────────────────────── */}
      <div>
        <p className="text-xs text-gray-400 mb-1 font-sans">
          Archaic &amp; numeral letters — Ϛ=6, Ϟ=90, Ϡ=900, Ϝ=digamma
        </p>
        <div className="flex flex-wrap gap-1">
          {ARCHAIC_ROW.map(k => (
            <button key={k.label} className={btnArchaic} title={k.title} onClick={() => onKey(k.value)}>
              {k.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── 4. Nomina sacra ─────────────────────────────────────── */}
      <div>
        <p className="text-xs text-gray-400 mb-1 font-sans">Nomina sacra (with combining overline)</p>
        <div className="flex flex-wrap gap-1">
          {NOMINA_SACRA.map(k => (
            <button key={k.label} className={btnNomen} title={k.title} onClick={() => onKey(k.value)}>
              {k.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── 5. Lowercase alphabet (collapsed) ───────────────────── */}
      <details className="group">
        <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600 list-none flex items-center gap-1">
          <span className="group-open:rotate-90 transition-transform inline-block">▶</span>
          Lowercase alphabet (minuscule manuscripts)
        </summary>
        <div className="space-y-1 mt-1.5">
          <div className="flex flex-wrap gap-1">
            {LOWER_ROW_1.map(ch => (
              <button key={ch} className={btnLower} title={ch} onClick={() => onKey(ch)}>
                {ch}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-1">
            {LOWER_ROW_2.map(ch => (
              <button key={ch} className={btnLower} title={ch} onClick={() => onKey(ch)}>
                {ch}
              </button>
            ))}
          </div>
        </div>
      </details>

      {/* ── 6. Corrector diacritics (combining marks) ───────────── */}
      <details className="group">
        <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600 list-none flex items-center gap-1">
          <span className="group-open:rotate-90 transition-transform inline-block">▶</span>
          Corrector marks (combining diacritics — attach to preceding letter)
        </summary>
        <div className="flex flex-wrap gap-1 mt-1.5">
          {CORRECTOR_MARKS.map(k => (
            <button key={k.value} className={btnDiacritic} title={k.title} onClick={() => onKey(k.value)}>
              {k.label}
            </button>
          ))}
        </div>
      </details>

    </div>
  )
}
