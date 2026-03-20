# aenigmata — Unmediated Ancient Greek Text Explorer

**aenigmata** is an open-source tool for digitizing, analyzing, and exploring ancient Greek manuscripts with the goal of recovering original meaning free from centuries of interpretive layering. Rather than producing a single authoritative translation, it builds a **semantic map** for each word — showing the full range of attested meanings across the target period (roughly 5th century BCE through 5th century CE), sourced from both secular and religious corpora, so readers can navigate the possibilities themselves.

## The Problem

The overwhelming majority of translations and scholarly apparatus for ancient Greek texts — particularly biblical and Septuagint manuscripts — have been produced within an ecclesiastical tradition that carries accumulated theological bias. Words have been narrowed to fit doctrinal frameworks. Alternative meanings attested in contemporary secular usage have been suppressed or ignored. The rich polysemy of ancient Greek has been flattened into single-word equivalents that serve institutional narratives.

## The Approach

aenigmata takes a different path:

1. **Digitize directly from manuscript images** using OCR trained on ancient scribal hands, preserving variant readings and confidence scores rather than collapsing to a single transcription.
2. **Build a lexical engine grounded in period sources** — prioritizing how words were actually used from the 5th century BCE through the 5th century CE across the full breadth of Greek literature, not just within Christian texts.
3. **Present an exploration interface** where every word is a doorway into its full semantic profile — multiple definitions, usage examples, semantic fields, and provenance for every claim — rather than a single "translation."

No word is given a single meaning. No interpretive tradition is privileged. The reader assembles understanding from evidence.

## Target Texts

- **Codex Vaticanus** (Vat.gr.1209) — one of the oldest and most complete manuscripts of the Greek Bible
- **Septuagint** (LXX) — the ancient Greek translation of the Hebrew scriptures, treated as a translation artifact whose choices are data, not doctrine
- Additional manuscripts and texts as the project matures

## Core Features

- **Multi-hypothesis OCR**: Manuscript images → ranked candidate readings with confidence scores and folio coordinates
- **Period-aware lexical database**: Word meanings sourced from contemporary (ancient) lexicons and corpora, with full provenance
- **Semantic field mapping**: Ancient Greek words mapped to clusters of modern-language terms that together approximate the original semantic range
- **Bias detection**: Computational flagging of words whose meaning diverges between Christian and secular contemporary usage
- **Interactive exploration UI**: Web interface where each word links to its full semantic profile
- **Annotated PDF export**: Static output for offline study and sharing

## Project Status

🚧 **Early development** — Architecture defined, initial implementation in progress.

See [TODO.md](./TODO.md) for the current roadmap and [ARCHITECTURE.md](./ARCHITECTURE.md) for technical design.

## Philosophy

This project is built on the conviction that ancient texts belong to everyone, not to the institutions that have claimed interpretive authority over them. Every design decision prioritizes:

- **Transparency**: Every definition, every translation suggestion carries its source and date
- **Plurality**: Multiple meanings are the norm, not the exception
- **Openness**: Built exclusively on freely available resources, fully open-source
- **Honesty**: Where knowledge is uncertain, we show uncertainty rather than false confidence

## Tech Stack

- **Python** — OCR pipeline, NLP processing, data ingestion
- **TypeScript/React** — Web exploration interface
- **SQLite + JSON** — Lexical database (portable, forkable, zero infrastructure)
- **Kraken/eScriptorium** — Historical manuscript OCR
- **CLTK + Morpheus** — Ancient Greek morphological analysis


## Contributing

This project welcomes contributors from all backgrounds — classicists, developers, linguists, historians, and curious readers. See [CONTRIBUTING.md](./CONTRIBUTING.md) (coming soon) for guidelines.

## License

MIT — because knowledge should be free.

## Resources & Acknowledgments

This project builds on the work of many open projects and institutions:

- [Perseus Digital Library](http://www.perseus.tufts.edu/) — Open Greek texts and lexical data
- [CLTK (Classical Language Toolkit)](https://cltk.org/) — NLP for classical languages
- [Kraken OCR](https://kraken.re/) — Historical document recognition
- [eScriptorium](https://escriptorium.readthedocs.io/) — Manuscript transcription platform
- [Vatican Digital Library](https://digi.vatlib.it/) — Digitized manuscript images
- [Logeion (UChicago)](https://logeion.uchicago.edu/) — Greek lexicon aggregator
- [SWORD/CrossWire](https://crosswire.org/) — Open biblical text modules
