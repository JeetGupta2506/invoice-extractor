```
PER-DOCUMENT RESULTS  (✓ = matches ground truth)
doc      source       status          review    is_inv  vendor  inv_no    date    curr   lines     tax   total   rows ok
------------------------------------------------------------------------------------------------------------------------
L01.pdf  pdf_digital  ok              no             ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓       4/4
L02.jpg  image        ok              no             ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓       6/6
L03.pdf  pdf_digital  failed          yes            ✗       ✗       ✗       ✗       ✗       ✗       ✗       ✗       0/4
L04.pdf  pdf_digital  ok              no             ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓     24/24
L05.pdf  pdf_digital  ok              no             ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓     10/10
L06.pdf  pdf_digital  failed          yes            ✗       ✗       ✗       ✗       ✗       ✗       ✗       ✗       0/4
L07.pdf  pdf_digital  failed          yes            ✗       ✗       ✗       ✗       ✗       ✗       ✗       ✗       0/4
L08.pdf  pdf_digital  failed          yes            ✗       ✗       ✗       ✗       ✗       ✗       ✗       ✗       0/0
L09.pdf  pdf_scanned  failed          yes            ✗       ✗       ✗       ✗       ✗       ✗       ✗       ✗       0/5
L10.pdf  pdf_scanned  failed          yes            ✗       ✗       ✗       ✗       ✗       ✗       ✗       ✗       0/5

FIELD-LEVEL ACCURACY
field               all docs           invoices only        
                      (n=10)                   (n=9)
is_invoice           4/10    40.0%         4/9     44.4%
vendor               4/10    40.0%         4/9     44.4%
invoice_number       4/10    40.0%         4/9     44.4%
invoice_date         4/10    40.0%         4/9     44.4%
currency             4/10    40.0%         4/9     44.4%
line_items           4/10    40.0%         4/9     44.4%
tax_total            4/10    40.0%         4/9     44.4%
total                4/10    40.0%         4/9     44.4%
ALL FIELDS          32/80    40.0%   (field-level micro average)
PERFECT DOCS         4/10    40.0%   (every field correct)

LINE ITEMS, ROW LEVEL: 44 rows fully correct | recall 66.7% of 66 gold rows | precision 100.0% of 44 predicted rows

ERRORS (prediction vs ground truth)
  L03.pdf  is_invoice     got None, expected True
  L03.pdf  vendor         got None, expected 'Kaveri Office Mart Pvt Ltd'
  L03.pdf  invoice_number got None, expected 'KOM/26-27/00418'
  L03.pdf  invoice_date   got None, expected '2026-06-23'
  L03.pdf  currency       got None, expected 'INR'
  L03.pdf  line_items     no prediction
  L03.pdf  tax_total      got None, expected 9788.4
  L03.pdf  total          got None, expected 64168.4
  L06.pdf  is_invoice     got None, expected True
  L06.pdf  vendor         got None, expected 'Anand & Rao Associates'
  L06.pdf  invoice_number got None, expected 'AR/2026/0093'
  L06.pdf  invoice_date   got None, expected '2026-05-30'
  L06.pdf  currency       got None, expected 'INR'
  L06.pdf  line_items     no prediction
  L06.pdf  tax_total      got None, expected 10933.2
  L06.pdf  total          got None, expected 71673.2
  L07.pdf  is_invoice     got None, expected True
  L07.pdf  vendor         got None, expected 'Pixel Harbor Studio'
  L07.pdf  invoice_number got None, expected 'PHS-1042'
  L07.pdf  invoice_date   got None, expected '2026-03-14'
  L07.pdf  currency       got None, expected 'USD'
  L07.pdf  line_items     no prediction
  L07.pdf  tax_total      got None, expected 334.13
  L07.pdf  total          got None, expected 4384.13
  L08.pdf  is_invoice     got None, expected False
  L08.pdf  vendor         got None, expected None
  L08.pdf  invoice_number got None, expected None
  L08.pdf  invoice_date   got None, expected None
  L08.pdf  currency       got None, expected None
  L08.pdf  line_items     no prediction
  L08.pdf  tax_total      got None, expected None
  L08.pdf  total          got None, expected None
  L09.pdf  is_invoice     got None, expected True
  L09.pdf  vendor         got None, expected 'Coastal Fresh Seafoods'
  L09.pdf  invoice_number got None, expected 'CFS-4471'
  L09.pdf  invoice_date   got None, expected '2026-10-14'
  L09.pdf  currency       got None, expected 'INR'
  L09.pdf  line_items     no prediction
  L09.pdf  tax_total      got None, expected 2032.5
  L09.pdf  total          got None, expected 42682.5
  L10.pdf  is_invoice     got None, expected True
  L10.pdf  vendor         got None, expected 'Metro Auto Parts'
  L10.pdf  invoice_number got None, expected 'MAP/D/09-0312'
  L10.pdf  invoice_date   got None, expected '2026-09-03'
  L10.pdf  currency       got None, expected 'INR'
  L10.pdf  line_items     no prediction
  L10.pdf  tax_total      got None, expected 19689.6
  L10.pdf  total          got None, expected 90009.6

REVIEW FLAG vs ACTUAL ERRORS
  flagged docs: 6/10  |  docs with >=1 wrong field: 6/10
  flagged AND wrong: 6  |  wrong but NOT flagged: 0  |  flagged but correct: 0
  share of wrong fields that sit in flagged docs: 48/48 (100.0%)
    L03.pdf: llm_error: server_error
    L06.pdf: llm_error: server_error
    L07.pdf: llm_error: rate_limited
    L08.pdf: llm_error: rate_limited
    L09.pdf: llm_error: rate_limited
    L10.pdf: llm_error: rate_limited

COST
  model gemini-3.8-flash | thinking=low | input mode=image+text | prompt v1
  docs that called the LLM: 10 | docs needing a 2nd round: 0
  avg tokens/doc: in 1,127 | out 248 | thinking 0
  avg cost/doc: $0.001774 | total for 10 docs: $0.01774
  avg latency/doc: 14.7s
  prices: https://ai.google.dev/gemini-api/docs/pricing (Standard tier, checked 2026-11-21)
```
