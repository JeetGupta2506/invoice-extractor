```
PER-DOCUMENT RESULTS  (✓ = matches ground truth)
doc      source       status          review    is_inv  vendor  inv_no    date    curr   lines     tax   total   rows ok
------------------------------------------------------------------------------------------------------------------------
L01.pdf  pdf_scanned  ok              no             ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓       4/4
L02.pdf  pdf_scanned  ok              no             ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓       6/6
L03.pdf  pdf_scanned  ok              no             ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓       4/4
L04.pdf  pdf_scanned  ok              no             ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓     24/24
L05.pdf  pdf_scanned  ok              no             ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓     10/10
L06.pdf  pdf_scanned  ok              no             ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓       4/4
L07.pdf  pdf_scanned  ok              no             ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓       4/4
L08.pdf  pdf_scanned  ok              no             ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓       0/0
L09.pdf  pdf_scanned  ok              no             ✓       ✓       ✗       ✓       ✓       ✗       ✓       ✓       4/5
L10.pdf  pdf_scanned  ok              no             ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓       5/5

FIELD-LEVEL ACCURACY
field               all docs           invoices only        
                      (n=10)                   (n=9)
is_invoice          10/10   100.0%         9/9    100.0%
vendor              10/10   100.0%         9/9    100.0%
invoice_number       9/10    90.0%         8/9     88.9%
invoice_date        10/10   100.0%         9/9    100.0%
currency            10/10   100.0%         9/9    100.0%
line_items           9/10    90.0%         8/9     88.9%
tax_total           10/10   100.0%         9/9    100.0%
total               10/10   100.0%         9/9    100.0%
ALL FIELDS          78/80    97.5%   (field-level micro average)
PERFECT DOCS         9/10    90.0%   (every field correct)

LINE ITEMS, ROW LEVEL: 65 rows fully correct | recall 98.5% of 66 gold rows | precision 98.5% of 66 predicted rows

ERRORS (prediction vs ground truth)
  L09.pdf  invoice_number got 'CFS-4473', expected 'CFS-4471'
  L09.pdf  line_items     row 2: quantity 20 != 18

REVIEW FLAG vs ACTUAL ERRORS
  flagged docs: 0/10  |  docs with >=1 wrong field: 1/10
  flagged AND wrong: 0  |  wrong but NOT flagged: 1  |  flagged but correct: 0
  share of wrong fields that sit in flagged docs: 0/2 (0.0%)

COST
  model gemini-3.5-flash-lite | thinking=minimal | input mode=image | prompt v1
  docs that called the LLM: 10 | docs needing a 2nd round: 0
  avg tokens/doc: in 2,115 | out 603 | thinking 0
  avg cost/doc: $0.002142 | total for 10 docs: $0.02142
  avg latency/doc: 5.1s
  prices: https://ai.google.dev/gemini-api/docs/pricing (Standard tier, checked 2026-11-21)
```
