# Invoice Extraction Pipeline

Reads an invoice (PDF or image) and returns validated JSON in the assignment schema,
with an eval harness that scores it field by field against the labelled set.

* **Report** (approach, accuracy, failure analysis, cost): [REPORT.md](REPORT.md)
* **Outputs for all 20 sample documents**: [outputs/](outputs/) (`Lxx.json` / `Uxx.json`),
  with validation and cost metadata per document in [outputs/meta/](outputs/meta/)

## Setup (fresh clone)

Requires Python 3.11+.

```bash
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then put your key in .env: GEMINI_API_KEY=...
```

Get a Gemini API key at <https://aistudio.google.com/apikey>.

**Sample documents.** They are confidential, so they are not in this repo. Unzip the sample
pack so that the folder looks like this:

```
data/sample_pack/labelled/L01.pdf, L01.json, ...
data/sample_pack/unlabelled/U01.pdf, ...
```

## Run

```bash
# one document -> JSON on stdout
python extract.py data/sample_pack/labelled/L01.pdf > out.json

# same, plus validation checks, needs_review, token counts and cost
python extract.py data/sample_pack/labelled/L01.pdf --meta

# all 20 documents -> outputs/
python extract.py --batch data/sample_pack/labelled data/sample_pack/unlabelled --out outputs

# EVAL: run on the 10 labelled documents, compare with ground truth, print the table
python evaluate.py

# score the committed outputs/ without an API key
python evaluate.py --offline

# tests (no API key needed)
python -m pytest -q

# web UI + HTTP API (bonus): upload a document, see the fields and checks beside it
uvicorn app:app --port 8000          # open http://localhost:8000 ; API: POST /extract (multipart "file")

# experiments in REPORT.md: stress set, ablations, repeatability, model comparison (~$0.30)
python scripts/make_stress_set.py
bash scripts/run_experiments.sh
```

Exit codes for `extract.py <file>`: `0` ok, `2` extracted but `needs_review`, `3` rejected or failed
(stdout then contains `{"error": {"code": ..., "message": ...}}`).

LLM responses are cached in `.cache/` keyed on file bytes + model + prompt version + settings,
so re-running the eval is free and reproducible. Use `--no-cache` to force fresh API calls.

## How it works

```
file ──► loader ──► LLM (Gemini) ──► parse + Pydantic ──► checks ──┬─► ok
         │           page images +                                  │
         │           PDF text layer                                 ├─► error check failed? retry once with the
         │                                                          │   failures fed back ──► still failing: "flagged"
         └─► rejected (corrupt / empty / blank / wrong type)        └─► warnings ──► needs_review = true
```

| File | What it does |
|---|---|
| `invoice_extractor/loader.py` | Detects the type from file bytes, renders PDF pages to images, pulls the PDF text layer, rejects bad inputs |
| `invoice_extractor/prompts.py` | System prompt (built from the sample pack's labelling conventions) |
| `invoice_extractor/llm.py` | Gemini call: JSON-schema output, timeout, retries with backoff, response cache, token usage |
| `invoice_extractor/schema.py` | Pydantic models: the output contract, and the richer object the LLM fills in |
| `invoice_extractor/validate.py` | Schema check (Pydantic + the provided JSON Schema), totals check, cross-checks |
| `invoice_extractor/pipeline.py` | Orchestration, retry/flag policy, cost accounting |
| `invoice_extractor/matching.py` | Eval matching rules |
| `extract.py` / `evaluate.py` | CLIs |

## Bad-input handling

* **Non-invoices** (purchase order, bank statement, cover letter): the model classifies
  `document_type`, and the code sets `is_invoice=false` with every other field `null`.
* **Extra case chosen: unreadable / corrupt files.** These are caught *before* any API call, so
  they cost nothing. The file type comes from the file's bytes, not its extension. Each case returns
  a stable error code: `empty_file`, `corrupt_pdf`, `encrypted_pdf`, `corrupt_image`, `unsupported_type`,
  `blank_document`, `too_many_pages`, `file_too_large`. Try `python extract.py bad_inputs/corrupt.pdf`.
* **Also handled: API failures.** There is a 90 s timeout, and timeouts, HTTP 429 and 5xx errors are
  retried with exponential backoff (4 attempts). After that the document gets `status=failed` with
  `error.code` = `timeout` / `rate_limited` / `server_error`, and no partial data is returned.
