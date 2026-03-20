# Contributing to aenigmata

Thank you for your interest in contributing. This document covers the practical process. For the project's goals and architecture, read [README.md](README.md) and [ARCHITECTURE.md](ARCHITECTURE.md) first — understanding the mission matters here.

---

## Ground rules

- **Every piece of data needs a source.** No definition, attestation, or derived value enters the database without a `source_id`. This is enforced by the schema (`NOT NULL` foreign keys) and it is non-negotiable.
- **No privileged tradition.** The project does not pick a "correct" reading. Secular, Christian, Jewish, and philosophical attestations are all presented equally with their tradition labels.
- **Prefer transparency over authority.** When in doubt, show the data and its origin rather than collapsing multiple possibilities into one answer.

---

## Setting up

```bash
git clone <repo>
cd aenigmata
./scripts/setup.sh
```

The setup script handles the conda environment, pip install, database initialization, and frontend dependencies. See [scripts/setup.sh](scripts/setup.sh) for what it does step by step.

Requirements:
- Python 3.11+
- [conda](https://docs.conda.io/) (recommended) or a plain venv
- Node.js 20+ (for the frontend)
- Tesseract 5+ (installed by conda via `environment.yml`)

---

## Branch and commit conventions

- Branch names: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`, `refactor/<topic>`
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
  - `feat:` — new functionality
  - `fix:` — bug fixes
  - `docs:` — documentation only
  - `refactor:` — code restructuring, no behaviour change
  - `test:` — adding or correcting tests
  - `chore:` — tooling, dependencies, config
- One logical change per commit. Keep commits small and focused.
- Always run `pytest tests/` and `ruff check src/ tests/` before pushing.

---

## Python conventions

- Type hints on all public functions and methods.
- Docstrings on all public functions (Google style).
- f-strings for string formatting.
- `pathlib.Path` for all file paths — no bare strings.
- Dataclasses or Pydantic models for structured data.
- No bare `except:` — always catch specific exceptions.
- All SQL queries use parameterized statements. Never interpolate user input into SQL.
- Line length: 100 characters (`ruff` enforces this).

---

## TypeScript / React conventions

- Functional components with hooks — no class components.
- Props interfaces defined explicitly above the component.
- Tailwind for styling — no CSS modules or inline style objects.
- Avoid `any` — use proper types or `unknown` with a type guard.

---

## Adding a lexical source

1. Research the source's terms of use. Only open-access or CC-licensed material.
2. Register the source in the `sources` table: name, type, license, bias_notes.
3. Write an ingestion script in `src/lexicon/ingest/<source_name>.py`.
   Every inserted row must carry the registered `source_id`.
4. Run deduplication against existing lemmas using shared utilities.
5. Add a test in `tests/test_lexicon.py` that verifies the ingestion produces valid, non-orphaned data.
6. Document the source's known biases in `bias_notes` — honestly.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full ingestion pattern.

---

## Adding a manuscript source

1. Write a `ManuscriptReader` subclass in `src/ocr/readers/`.
2. Implement all four abstract methods: `get_manuscript_id()`, `list_folios()`, `get_folio_image()`, `get_folio_metadata()`.
3. Export from `src/ocr/readers/__init__.py`.
4. Add a test in `tests/test_ocr.py`.

No changes to the OCR pipeline are needed — it depends only on the `ManuscriptReader` interface.

---

## Running tests and linting

```bash
pytest tests/ -v
ruff check src/ tests/
mypy src/
```

All three must pass before a PR can be merged.

---

## Pull requests

- Open a PR against `main`.
- Describe *what* changed and *why* — link to the relevant TODO item if applicable.
- Keep PRs focused. A PR that adds a lexical source should not also refactor unrelated code.
- The CI must be green before review.

---

## Questions

Open an issue. Discussions about interpretive choices (tradition labeling, source selection, schema decisions) are especially welcome — these are the hard parts of the project.
