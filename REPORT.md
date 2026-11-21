# Report: Invoice Extraction Pipeline

**TL;DR**
* On the 10 labelled documents the pipeline got **every field right (80/80 fields, 66/66 line-item rows)**.
  The result is the same across 3 runs. Average cost is **$0.0023 per document** (about 2,500 input and 600
  output tokens) and latency is about 5 s.
* Ten clean documents can't show where the pipeline fails. With 10/10 correct, a 95% confidence interval only
  says document-level accuracy is above ~72%. So I built a **stress set**: the same 10 documents, degraded 6 ways
  (60 runs). That is where every error in this report comes from.
* The main risk is **silent digit misreads on poor scans**, above all in invoice numbers, which have no arithmetic
  check. The `needs_review` flag catches **88% of wrong documents** on the stress set. This used checks I revised
  after looking at that set, so the number is optimistic; with the original checks it was 44%.
* Two things did not work: **the corrective retry fixed 0 of 6 cases**, and **the PDF text layer added cost
  (+18% input tokens) with no measurable accuracy gain** on this set.

---

## 1. Approach

### Model and why
**`gemini-3.5-flash-lite`** (Google Gemini API), with temperature 0 and thinking set to `minimal`.
* It accepts page images directly, which is needed: 5 of the 20 documents are scans or phone photos with no text layer.
* It supports **JSON-schema-constrained output** (`response_json_schema`), so the output always parses.
* It is cheap: $0.30 / $2.50 per 1M input/output tokens, and there is a free tier for development.

### Input: page images plus the PDF text layer
Every page is rendered to an image at 150 dpi (PyMuPDF); photos are sent as JPEG. For digital PDFs the text layer is
sent as well, with the instruction: *use the image for layout (which block is the seller, which column is which) and
the text for exact characters*. Scans and photos go in as images only. Why both: vision alone can misread digits,
and text alone loses the layout. In `L01` and `U09`, for example, the text layer interleaves the "Bill to" and
"From" blocks. Section 1.5 measures whether this was worth it.

### Prompting
* A system prompt (`invoice_extractor/prompts.py`). Step 1 classifies the document type; only `invoice` counts.
  The prompt says purchase orders, statements, quotes, receipts and letters are not invoices *even if they contain
  amounts and tax*, and that the document's own title is the strongest signal. Step 2 gives extraction rules.
* The rules restate the **labelling conventions from the sample pack's README**: vendor is the seller at the top;
  the date is the issue date, not the due date; discounts are negative line items; `tax_total` is the sum of the tax
  lines, or 0 when there is no tax. The prompt also covers regional number formats (`2,68,290.00`, `1.029,00`) and
  day-first vs month-first dates in context. It tells the model to *copy numbers as printed, never "fix"
  arithmetic*, so the validator sees the document as it really is.
* **The model fills a richer schema than the output** (`LLMExtraction`). On top of the required fields it gives
  `document_type`, `subtotal`, a `unit_price` per row, each tax line separately, the date exactly as printed, a
  `legibility` self-rating and `notes`. These extras are never returned; they exist so the code can cross-check
  the answer.
* Some steps are deterministic code rather than left to the model. `is_invoice` is derived from `document_type`,
  so the two can't contradict each other. Non-invoices are forced to all-null. `tax_total` is computed as the sum
  of the tax lines, and amounts are rounded to cents.

### Validation, and what happens on failure
| Check | Severity | What happens |
|---|---|---|
| Pydantic model **and** the provided `schema.json` (jsonschema) | error | retry, then `failed` |
| Line items + tax = total, tolerance 0.01 × (rows + 2) | error | one corrective retry that names the failed check; if it still fails: `status=flagged`, `needs_review=true` |
| Required fields present (vendor, number, date, currency, total) | error | same |
| Printed subtotal = sum of rows; tax lines = model's tax_total; qty × unit price = amount | warning | `needs_review=true` |
| Ambiguous all-numeric date (e.g. `07/02/2026`); date plausible; known currency; legibility not "clear" | warning | `needs_review=true` |
| Scan or photo under 800 px on its short side (~100 dpi) | warning | `needs_review=true` |

Nothing passes silently. Every output has a `meta` record (`outputs/meta/*.meta.json`) listing every check with
its detail, the status (`ok` / `ok_after_retry` / `flagged` / `rejected` / `failed`), tokens and cost. On the CLI,
exit code 2 means "extracted, but needs review".

### Bad inputs
* **Non-invoices.** All 3 were classified correctly (L08 purchase order, U06 bank statement, U10 cover letter).
  L08 was correct in all 12 runs that processed it (6 settings on the clean set plus 6 degraded versions), even
  though it has a vendor, line items, GST and a total. The prompt's "title is the strongest signal" rule is what carries it.
* **Extra case chosen: corrupt or unreadable files.** These are caught *before* any API call, so they cost nothing.
  The file type is detected from its bytes, not its extension. Error codes: `empty_file`, `corrupt_pdf`,
  `encrypted_pdf`, `corrupt_image`, `unsupported_type` (e.g. a text file renamed `.pdf`), `blank_document`,
  `too_many_pages`, `file_too_large`. Demo files are in `bad_inputs/`, and the cases are tested.
* **API failures, which I actually hit.** Timeouts, 429 and 5xx errors are retried with exponential backoff. When
  the model ran out of its **free-tier daily quota** (20 requests per day for `gemini-3.8-flash`), the pipeline
  returned `status=failed` with a clear error for those documents and no partial data. It did, however, keep
  retrying an error that said "retry in 1h25m". I changed it so that a 429 asking for a wait of more than 60 s
  fails immediately with `quota_exhausted`.

### What did not work
1. **The corrective retry, as built, fixed nothing: 0 of 6.** On clean documents no retry was ever triggered. On
   the stress set, 6 documents failed the totals check and were retried with the failure described to the model.
   All 6 were still wrong afterwards. When the model can't read a digit, telling it the sum is off doesn't let it
   read the digit. Instead it re-reads the same pixels and gets the same answer, or a different wrong one. Each
   retry costs about $0.002. The retry still earns its place as the step before a flag, but it should **escalate to
   a stronger model or a higher-resolution crop** rather than repeat the same call. I couldn't test that: the
   stronger model's free-tier quota ran out.
2. **Sending the PDF text layer as well as the image** (my default) gave no measurable gain on the labelled set
   (both modes scored 80/80) and costs 18% more input tokens. I kept it anyway, for a reason the stress test
   supports: every digit error in this report comes from reading pixels, and for digital PDFs the text layer
   removes that risk. It's a defensible choice, not a proven one.
3. **My first quantity × unit price check was too loose.** It allowed 0.5% of the row amount, so in a degraded
   L09 a misread `20 × 700 = 14,040` passed, even though the model itself wrote in `notes` that the row didn't add
   up. The tolerance is now based on rounding: the unit price is printed to the cent, so the allowance is
   `0.01 + |qty| × 0.005`. The same fix showed that a "planted error" I thought I'd found in U04
   (`1440 × 0.09 ≠ 122.40`) is actually consistent with a rate of $0.085 printed rounded to `0.09`. The old check
   flagged it wrongly.

---

## 2. Accuracy

`python evaluate.py`: per-document ✓/✗ table, field accuracy, row-level line-item precision/recall, an error list,
review-flag analysis and cost. Full output: [`eval_results/baseline.md`](eval_results/baseline.md).

### Labelled set (10 documents: 7 digital PDFs, 2 scanned PDFs, 1 phone photo; 1 non-invoice)

| Field | Correct | Accuracy |
|---|---|---|
| is_invoice | 10/10 | 100% |
| vendor | 10/10 | 100% |
| invoice_number | 10/10 | 100% |
| invoice_date | 10/10 | 100% |
| currency | 10/10 | 100% |
| line_items (whole table exact) | 10/10 | 100% (66/66 rows) |
| tax_total | 10/10 | 100% |
| total | 10/10 | 100% |
| **Documents with every field correct** | **10/10** | |

**How much to trust this:** not much on its own. It is 10 clean, synthetic documents. With 10/10, the 95% Wilson
interval for document-level accuracy is about **72–100%**; for the 66 rows it is about **95–100%**. A perfect score
here mainly shows the task is well within the model's ability on clean input, which is why I ran the stress tests.

**Same set, other settings** (each a full re-run on the 10 documents):

| Run | Fields correct | Perfect docs | Avg cost/doc | Notes |
|---|---|---|---|---|
| Baseline: flash-lite, image + text | 80/80 | 10/10 | $0.00226 | default |
| Repeat run 1 (no cache) | 80/80 | 10/10 | $0.00227 | identical scores; output length varies ±1% |
| Repeat run 2 (no cache) | 80/80 | 10/10 | $0.00225 | |
| Image only | 80/80 | 10/10 | $0.00215 | 15% fewer input tokens |
| Text layer only (scans fall back to image) | 80/80 | 10/10 | $0.00200 | |
| `gemini-3.1-flash-lite` (older, cheaper) | 80/80 | 10/10 | $0.00153 | 32% cheaper; 6.9 s vs 4.7 s latency |
| `gemini-3.8-flash` (stronger) | 32/32 on 4 docs | 4/4 | $0.00443 | **the other 6 hit the free-tier daily quota**, so this comparison is incomplete |

### Stress test (scripts/make_stress_set.py)
Each labelled document was re-rendered as an image-only scan with no text layer, under 6 degradations, keeping the
same ground truth. 60 document-runs:

| Variant | is_inv | vendor | inv_no | date | curr | lines | tax | total | Perfect docs | Rows correct |
|---|---|---|---|---|---|---|---|---|---|---|
| rot90 (like U05) | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | **10/10** | 66/66 |
| rot180 (upside down) | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | **10/10** | 66/66 |
| phone (5° skew, shadow, blur) | 10 | 10 | 9 | 10 | 10 | 9 | 10 | 10 | 9/10 | 65/66 |
| lowres (75 dpi, JPEG q35) | 10 | 10 | 9 | 10 | 10 | 9 | 10 | 10 | 8/10 | 65/66 |
| blur_noise (100 dpi, blur, noise) | 10 | 10 | 8 | 9 | 10 | 6 | 8 | 9 | 5/10 | 57/66 |
| tiny (50 dpi, JPEG q30) | 10 | 10 | 5 | 8 | 10 | 3 | 7 | 8 | 2/10 | 53/66 |

What holds up under every degradation: **classification, vendor and currency (60/60 each)**, and **rotation**
(no errors, so no rotation-correction step is needed). What breaks: **digits**.

### Matching rules (`invoice_extractor/matching.py`)
| Field | Rule |
|---|---|
| is_invoice | exact boolean |
| vendor | case, punctuation and whitespace ignored; `&` = `and`; trailing legal suffixes ignored (Pvt, Ltd, LLP, Inc, GmbH, B.V., Co, …). So `"Acme Pvt Ltd"` = `"Acme"`, but `"Acme Supplies"` ≠ `"Acme"`. No fuzzy matching: one wrong letter is wrong. (The model returns all-caps names as printed, e.g. `ORBIT HARDWARE SUPPLIES`; the labels use title case, so case is ignored.) |
| invoice_number | exact, ignoring case, whitespace and a leading `#`. Slashes, dashes and zeros must match: `KOM/26-27/418` ≠ `KOM/26-27/00418` |
| invoice_date | same calendar date (ISO) |
| currency | exact ISO code |
| tax_total, total | within 0.01 after parsing, so `"1,200.00"` = `1200`, `"₹2,68,290.00"` = `268290`, `"1.029,00"` = `1029` |
| line_items | correct only if the row count matches and every row, *in order*, has amount within 0.01, the same quantity (null = null) and description similarity ≥ 0.85 (difflib, after normalisation, to tolerate a dropped comma). Row-level precision and recall are reported separately. |
| nulls | null = null is correct (that is how a non-invoice scores on extraction fields); null vs a value is wrong. A document that fails or is rejected scores wrong on every field. |

Accuracy is shown over all 10 documents and over the 9 invoices only. Both are in the eval output.

---

## 3. Failure analysis

All 33 wrong fields come from the stress set (the clean set had none). Grouped by cause:

| # | Cause | Wrong fields (of 33) | Caught by review flag? | Examples |
|---|---|---|---|---|
| A | **Digit or letter misread in an identifier** | 9 (all invoice_number) | Only when something else on the page also failed. Nothing checks an ID's arithmetic | `NWL-88213` → `NWL-58213`, `OHS-0261-26` → `DHS-0261-26` (O→D), `PHS-1042` → `PHS-1842`, `MAP/D/09-0312` → `MAP/D/20-0312` |
| B | **Digit misread in an amount or quantity that breaks the arithmetic** | 12 | **Yes**: totals check (or qty × price), then flagged | L07 tiny: `850` → `350` (total off by 500); L02 blur: `560` → `960`; L04 tiny: three rows wrong, off by 1,300; L09 75 dpi: quantity `18` → `20` (qty × price check) |
| C | **Plausible invention**: at very low legibility the model produces *internally consistent* numbers | 6 (L09 tiny and blur: lines, tax, total) | Not by arithmetic, which all passes. Only by the resolution check (tiny) or the model's own "partly legible" (blur) | L09 blur: all 5 rows changed (`12.5 × 920` → `22.5 × 500`); every row multiplies out, tax is exactly 2.5% + 2.5% and the total adds up. In the tiny version the model rated the page **"clear"**. |
| D | **Compensating errors**: misreads that cancel out | 3 | **No** (arithmetic) | L05 blur: row 7 `3,840` → `3,800` and IGST `12,708.90` → `12,748.90`, so the total still matches. L06 tiny: one row −200, another +200 |
| E | **Date misread** | 3 | Partly | Year `2026` → `2020` (L05, L10 tiny, which passes the plausibility check); day `14` → `24` (L09 blur) |

Some line-item errors also include **description drift** (`Crab (live)` → `Crab claws`, `front (sedan)` →
`front (radial)`): the model fills in a plausible word it couldn't read.

**What this says:** the pipeline doesn't fail on *understanding* the document (layout, classification, vendor vs
buyer, regional formats and rotation all held up perfectly). It fails on *reading pixels* when they are poor. The
most dangerous failures are the ones that look right: A, C and D.

### What I would fix first
1. **Invoice numbers on scans (cause A).** It is the most frequent single error (9 of 33), it matters most to
   finance (it's the deduplication and payment-reference key), and the arithmetic checks can't see it. The fix: for
   scans and photos, do a second read of only the header fields, from a crop at twice the resolution and/or by a
   stronger model, and set `needs_review` when the two reads disagree. It costs about $0.001 per scanned document.
   A cheaper partial check: many invoices print the number twice (header and footer), and the two readings can be
   compared.
2. **A tax-rate check (cause D).** Read the rate from the tax label (`IGST @ 18%`) and check tax ≈ rate × taxable
   amount. This would have caught L05. It has to handle mixed rates: U01 has 3 GST rates and U08 has 2 VAT rates.
3. **Make the retry escalate (see "what did not work").** Retry with a stronger model or a sharper crop instead of
   the same call. The current retry costs money and fixed nothing.

### Review flag (bonus): does it catch the errors?

| Data | Flagged docs | Wrong docs | Wrong docs that were flagged (recall) | Flagged docs that were wrong (precision) | Wrong *fields* inside flagged docs |
|---|---|---|---|---|---|
| Labelled, clean | 0/10 | 0/10 | n/a | n/a | n/a |
| Stress, **v1 checks** (before this analysis) | 8/60 | 16/60 | 7/16 = **44%** | 7/8 = 88% | 18/33 = 55% |
| Stress, **v2 checks** (current) | 23/60 | 16/60 | 14/16 = **88%** | 14/23 = 61% | 29/33 = **88%** |
| 20 real documents (manual check) | 1/20 (U09) | 0 found | n/a | 0/1 | n/a |

* The v2 changes (the rounding-based line-math tolerance and the scan-resolution warning) **were designed after
  looking at the stress-test errors and are evaluated on the same stress set**, so the 88% is optimistic. The
  honest pre-analysis figure is the v1 line, 44%.
* The trade-off is deliberate: on the 75-dpi set, 9 documents are flagged and only 2 are wrong. For a finance team
  I think "every low-resolution scan gets a human glance" is the right default. If reviewer time matters more, the
  800 px threshold can be lowered.
* The one flag on real data (U09, `07/02/2026`) is a **false positive**: the due date `21/02/2026` on the same page
  proves the document is day-first. The improvement would be to clear the ambiguity flag when another date on the
  page settles it.
* What still gets through: the 2 invoice-number misreads and the compensating error described above.

### Unlabelled documents
There is no ground truth. I compared all 10 outputs by hand against the documents and found no errors. That
includes the 90°-rotated scan (U05), the blurry photo with a US date (U02 → `2026-09-14`), German and Dutch number
formats (U07, U08), three GST rates summed (U01: 2,592 + 271.50 + 117 = 2,980.50), a service-charge row with no
quantity (U09), "reverse charge, $0.00" tax (U04), and two non-invoices (U06 statement, U10 cover letter). This is
my reading, not ground truth.

---

## 4. Cost per document

**Method.** Every API response includes `usage_metadata` (prompt tokens, output tokens, thinking tokens). The
pipeline records it for every call, including retries, and computes
`cost = input × $0.30/1M + (output + thinking) × $2.50/1M`, using Google's published Standard-tier prices for
`gemini-3.5-flash-lite` ([pricing page](https://ai.google.dev/gemini-api/docs/pricing), checked 2026-11-21; see
`invoice_extractor/pricing.py`). These are **measured token counts, not estimates**. I ran on the free tier, so the
actual bill was $0; all figures are what the paid tier would charge.

| | Input tokens | Output tokens | Thinking tokens | Cost |
|---|---|---|---|---|
| **Average per document (labelled set)** | **2,506** | **605** | 0 | **$0.00226** |
| Cheapest (L08, a non-invoice: short answer) | 2,458 | 128 | 0 | $0.00106 |
| Most expensive (L04: 2 pages, 24 line items) | 4,299 | 1,718 | 0 | $0.00558 |
| All 20 documents (`outputs/`) | 2,422 avg | 484 avg | 0 | $0.00194 avg, **$0.039 total** |

* **Where the cost goes:** a one-page scan is about 2,000 input tokens (system prompt, JSON schema and one image).
  The text layer of a digital PDF adds ~350–450. The 2-page L04 with its text layer is 4,299. Output tokens cost
  about 8× more each, so **cost grows with the number of line items**.
* **Per 1,000 invoices:** about $2.30 (image + text), $2.15 (image only), $1.55 (`gemini-3.1-flash-lite`), or about
  $4.40 with `gemini-3.8-flash` (introductory price, which doubles in January 2027).
* **Retries add cost:** on the 50-dpi stress set, 4 retries pushed the average to $0.0035 per document.
* **Total spent building this:** 134 API calls (114 cached plus 20 for the repeat runs), about **$0.30 at paid-tier
  prices** ($0 actually charged).

---

## 5. Honesty notes: tuning and overfitting

* **The prompt (v1) was written from the sample pack's README before any model run and never changed.** The
  labelled-set numbers above come from the first and only prompt version. They are not the result of iterating on
  the 10 labelled documents.
* **The validator *was* changed after looking at results**, specifically at the stress-test errors (line-math
  tolerance and scan resolution). The review-flag numbers for v2 are therefore measured on the same data that
  motivated the changes; the v1 numbers are also reported.
* The stress set is derived from the labelled documents, so it tests robustness to image quality, not to new layouts.
* I looked at all 20 documents while designing (to understand the formats). The prompt rules are general, but some
  (regional number formats, day-first dates) were worded with examples of the kind seen in the pack.
* Limitations: 20 synthetic documents from what look like a handful of templates. Real vendor invoices have far more
  layout variety (stamps, handwriting, multi-currency, credit notes), so I would expect real-world accuracy to be
  well below 100%. Building a bigger labelled set would be the first job before trusting any of these numbers in
  production.

## Reproducing everything
```bash
python evaluate.py                    # labelled set (cached; --no-cache for fresh calls)
python scripts/make_stress_set.py     # build data/stress/*
bash scripts/run_experiments.sh       # ablations, stress, repeats, model comparison -> eval_results/
```
Earlier results with the v1 checks are kept in `eval_results/v1_checks/`.
