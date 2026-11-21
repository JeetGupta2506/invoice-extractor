```
PER-DOCUMENT RESULTS  (✓ = matches ground truth)
doc      source       status          review    is_inv  vendor  inv_no    date    curr   lines     tax   total   rows ok
------------------------------------------------------------------------------------------------------------------------
L01.pdf  pdf_scanned  ok              no             ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓       4/4
L02.pdf  pdf_scanned  flagged         yes            ✓       ✓       ✓       ✓       ✓       ✗       ✓       ✓       5/6
L03.pdf  pdf_scanned  ok              no             ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓       4/4
L04.pdf  pdf_scanned  ok              yes            ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓     24/24
L05.pdf  pdf_scanned  ok              no             ✓       ✓       ✗       ✓       ✓       ✗       ✗       ✓      9/10
L06.pdf  pdf_scanned  ok              no             ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓       4/4
L07.pdf  pdf_scanned  ok              no             ✓       ✓       ✗       ✓       ✓       ✓       ✓       ✓       4/4
L08.pdf  pdf_scanned  ok              no             ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓       0/0
L09.pdf  pdf_scanned  ok              yes            ✓       ✓       ✓       ✗       ✓       ✗       ✗       ✗       0/5
L10.pdf  pdf_scanned  flagged         yes            ✓       ✓       ✓       ✓       ✓       ✗       ✓       ✓       3/5

FIELD-LEVEL ACCURACY
field               all docs           invoices only        
                      (n=10)                   (n=9)
is_invoice          10/10   100.0%         9/9    100.0%
vendor              10/10   100.0%         9/9    100.0%
invoice_number       8/10    80.0%         7/9     77.8%
invoice_date         9/10    90.0%         8/9     88.9%
currency            10/10   100.0%         9/9    100.0%
line_items           6/10    60.0%         5/9     55.6%
tax_total            8/10    80.0%         7/9     77.8%
total                9/10    90.0%         8/9     88.9%
ALL FIELDS          70/80    87.5%   (field-level micro average)
PERFECT DOCS         5/10    50.0%   (every field correct)

LINE ITEMS, ROW LEVEL: 57 rows fully correct | recall 86.4% of 66 gold rows | precision 86.4% of 66 predicted rows

ERRORS (prediction vs ground truth)
  L02.pdf  line_items     row 5: amount 960.0 != 560.0
  L05.pdf  invoice_number got 'OHS-8261-26', expected 'OHS-0261-26'
  L05.pdf  line_items     row 7: amount 3800.0 != 3840.0
  L05.pdf  tax_total      got 12748.9, expected 12708.9
  L07.pdf  invoice_number got 'PHS-1842', expected 'PHS-1042'
  L09.pdf  invoice_date   got '2026-10-24', expected '2026-10-14'
  L09.pdf  line_items     row 1: amount 11250.0 != 11500.0; quantity 22.5 != 12.5; row 2: amount 14000.0 != 14040.0; quantity 20 != 18; row 3: amount 5950.0 != 6080.0; quantity 8.5 != 9.5; row 4: amount 2800.0 != 2870.0; row 5: amount 5500.0 != 6160.0
  L09.pdf  tax_total      got 1975.0, expected 2032.5
  L09.pdf  total          got 41475.0, expected 42682.5
  L10.pdf  line_items     row 1: description 'Brake pad set, front (radial)' vs 'Brake pad set, front (sedan)' (sim 0.82); row 5: amount 5500.0 != 5580.0; quantity 10 != 18

REVIEW FLAG vs ACTUAL ERRORS
  flagged docs: 4/10  |  docs with >=1 wrong field: 5/10
  flagged AND wrong: 3  |  wrong but NOT flagged: 2  |  flagged but correct: 1
  share of wrong fields that sit in flagged docs: 6/10 (60.0%)
    L02.pdf: totals_reconcile: line items 20010.00 + tax 3529.80 = 23539.80 vs total 23139.80 (diff +400.00, tolerance 0.08); subtotal_matches_lines: sum of rows 20010.00 vs
    L04.pdf: legibility: model reported legibility=partly_legible
    L09.pdf: legibility: model reported legibility=partly_legible
    L10.pdf: totals_reconcile: line items 70240.00 + tax 19689.60 = 89929.60 vs total 90009.60 (diff -80.00, tolerance 0.07); subtotal_matches_lines: sum of rows 70240.00 vs

COST
  model gemini-3.5-flash-lite | thinking=minimal | input mode=image | prompt v1
  docs that called the LLM: 10 | docs needing a 2nd round: 2
  avg tokens/doc: in 2,669 | out 724 | thinking 0
  avg cost/doc: $0.002611 | total for 10 docs: $0.02611
  avg latency/doc: 7.8s
  prices: https://ai.google.dev/gemini-api/docs/pricing (Standard tier, checked 2026-11-21)
```
