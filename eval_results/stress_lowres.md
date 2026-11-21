```
PER-DOCUMENT RESULTS  (✓ = matches ground truth)
doc      source       status          review    is_inv  vendor  inv_no    date    curr   lines     tax   total   rows ok
------------------------------------------------------------------------------------------------------------------------
L01.pdf  pdf_scanned  ok              yes            ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓       4/4
L02.pdf  pdf_scanned  ok              yes            ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓       6/6
L03.pdf  pdf_scanned  ok              yes            ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓       4/4
L04.pdf  pdf_scanned  ok              yes            ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓     24/24
L05.pdf  pdf_scanned  ok              yes            ✓       ✓       ✗       ✓       ✓       ✓       ✓       ✓     10/10
L06.pdf  pdf_scanned  ok              yes            ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓       4/4
L07.pdf  pdf_scanned  ok              yes            ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓       4/4
L08.pdf  pdf_scanned  ok              no             ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓       0/0
L09.pdf  pdf_scanned  ok              yes            ✓       ✓       ✓       ✓       ✓       ✗       ✓       ✓       4/5
L10.pdf  pdf_scanned  ok              yes            ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓       5/5

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
PERFECT DOCS         8/10    80.0%   (every field correct)

LINE ITEMS, ROW LEVEL: 65 rows fully correct | recall 98.5% of 66 gold rows | precision 98.5% of 66 predicted rows

ERRORS (prediction vs ground truth)
  L05.pdf  invoice_number got 'DHS-0261-26', expected 'OHS-0261-26'
  L09.pdf  line_items     row 2: quantity 20 != 18

REVIEW FLAG vs ACTUAL ERRORS
  flagged docs: 9/10  |  docs with >=1 wrong field: 2/10
  flagged AND wrong: 2  |  wrong but NOT flagged: 0  |  flagged but correct: 7
  share of wrong fields that sit in flagged docs: 2/2 (100.0%)
    L01.pdf: scan_resolution: page is only 621px on its short side (< 800px, ~100 dpi)
    L02.pdf: scan_resolution: page is only 750px on its short side (< 800px, ~100 dpi)
    L03.pdf: scan_resolution: page is only 621px on its short side (< 800px, ~100 dpi)
    L04.pdf: scan_resolution: page is only 621px on its short side (< 800px, ~100 dpi)
    L05.pdf: scan_resolution: page is only 621px on its short side (< 800px, ~100 dpi)
    L06.pdf: scan_resolution: page is only 621px on its short side (< 800px, ~100 dpi)
    L07.pdf: scan_resolution: page is only 621px on its short side (< 800px, ~100 dpi)
    L09.pdf: line_math: row 2: 20 x 700 = 14000.00 but amount is 14040.00; scan_resolution: page is only 621px on its short side (< 800px, ~100 dpi)
    L10.pdf: scan_resolution: page is only 621px on its short side (< 800px, ~100 dpi)

COST
  model gemini-3.5-flash-lite | thinking=minimal | input mode=image | prompt v1
  docs that called the LLM: 10 | docs needing a 2nd round: 0
  avg tokens/doc: in 2,131 | out 609 | thinking 0
  avg cost/doc: $0.002162 | total for 10 docs: $0.02162
  avg latency/doc: 3.8s
  prices: https://ai.google.dev/gemini-api/docs/pricing (Standard tier, checked 2026-11-21)
```
