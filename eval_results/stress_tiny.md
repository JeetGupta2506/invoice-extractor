```
PER-DOCUMENT RESULTS  (✓ = matches ground truth)
doc      source       status          review    is_inv  vendor  inv_no    date    curr   lines     tax   total   rows ok
------------------------------------------------------------------------------------------------------------------------
L01.pdf  pdf_scanned  ok              yes            ✓       ✓       ✗       ✓       ✓       ✓       ✓       ✓       4/4
L02.pdf  pdf_scanned  ok              yes            ✓       ✓       ✓       ✓       ✓       ✗       ✓       ✓       4/6
L03.pdf  pdf_scanned  ok              yes            ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓       4/4
L04.pdf  pdf_scanned  flagged         yes            ✓       ✓       ✗       ✓       ✓       ✗       ✓       ✓     21/24
L05.pdf  pdf_scanned  flagged         yes            ✓       ✓       ✗       ✗       ✓       ✗       ✗       ✓      9/10
L06.pdf  pdf_scanned  ok              yes            ✓       ✓       ✓       ✓       ✓       ✗       ✓       ✓       2/4
L07.pdf  pdf_scanned  flagged         yes            ✓       ✓       ✓       ✓       ✓       ✗       ✓       ✓       3/4
L08.pdf  pdf_scanned  ok              no             ✓       ✓       ✓       ✓       ✓       ✓       ✓       ✓       0/0
L09.pdf  pdf_scanned  ok              yes            ✓       ✓       ✗       ✓       ✓       ✗       ✗       ✗       2/5
L10.pdf  pdf_scanned  flagged         yes            ✓       ✓       ✗       ✗       ✓       ✗       ✗       ✗       4/5

FIELD-LEVEL ACCURACY
field               all docs           invoices only        
                      (n=10)                   (n=9)
is_invoice          10/10   100.0%         9/9    100.0%
vendor              10/10   100.0%         9/9    100.0%
invoice_number       5/10    50.0%         4/9     44.4%
invoice_date         8/10    80.0%         7/9     77.8%
currency            10/10   100.0%         9/9    100.0%
line_items           3/10    30.0%         2/9     22.2%
tax_total            7/10    70.0%         6/9     66.7%
total                8/10    80.0%         7/9     77.8%
ALL FIELDS          61/80    76.2%   (field-level micro average)
PERFECT DOCS         2/10    20.0%   (every field correct)

LINE ITEMS, ROW LEVEL: 53 rows fully correct | recall 80.3% of 66 gold rows | precision 80.3% of 66 predicted rows

ERRORS (prediction vs ground truth)
  L01.pdf  invoice_number got 'NWL-58213', expected 'NWL-88213'
  L02.pdf  line_items     row 3: amount 250.0 != 350.0; row 6: amount 2300.0 != 2200.0
  L04.pdf  invoice_number got 'MPF-2026-0307', expected 'MPP-2026-0207'
  L04.pdf  line_items     row 6: amount 33000.0 != 35400.0; row 8: amount 4140.0 != 4740.0; row 19: amount 10720.0 != 6420.0; quantity 500 != 300
  L05.pdf  invoice_number got 'OHS-0261/20', expected 'OHS-0261-26'
  L05.pdf  invoice_date   got '2020-01-27', expected '2026-01-27'
  L05.pdf  line_items     row 3: amount 4260.0 != 9360.0
  L05.pdf  tax_total      got 12788.9, expected 12708.9
  L06.pdf  line_items     row 2: amount 6300.0 != 6500.0; row 4: amount 1440.0 != 1240.0
  L07.pdf  line_items     row 2: amount 350.0 != 850.0
  L09.pdf  invoice_number got 'CFS-4671', expected 'CFS-4471'
  L09.pdf  line_items     row 3: amount 6460.0 != 6080.0; row 4: amount 2040.0 != 2870.0; quantity 3 != 7; row 5: amount 4290.0 != 6160.0; description 'Crab claws, kg' vs 'Crab (live), kg' (sim 0.72)
  L09.pdf  tax_total      got 4312.5, expected 2032.5
  L09.pdf  total          got 42642.5, expected 42682.5
  L10.pdf  invoice_number got 'MAP/D/20-0312', expected 'MAP/D/09-0312'
  L10.pdf  invoice_date   got '2020-09-03', expected '2026-09-03'
  L10.pdf  line_items     row 5: amount 5560.0 != 5580.0; quantity 20 != 18
  L10.pdf  tax_total      got 19684.0, expected 19689.6
  L10.pdf  total          got 90004.0, expected 90009.6

REVIEW FLAG vs ACTUAL ERRORS
  flagged docs: 9/10  |  docs with >=1 wrong field: 8/10
  flagged AND wrong: 8  |  wrong but NOT flagged: 0  |  flagged but correct: 1
  share of wrong fields that sit in flagged docs: 19/19 (100.0%)
    L01.pdf: scan_resolution: page is only 414px on its short side (< 800px, ~100 dpi)
    L02.pdf: scan_resolution: page is only 500px on its short side (< 800px, ~100 dpi)
    L03.pdf: scan_resolution: page is only 414px on its short side (< 800px, ~100 dpi)
    L04.pdf: totals_reconcile: line items 269590.00 + tax 32194.80 = 301784.80 vs total 300484.80 (diff +1300.00, tolerance 0.26); subtotal_matches_lines: sum of rows 269590
    L05.pdf: totals_reconcile: line items 65505.00 + tax 12788.90 = 78293.90 vs total 83313.90 (diff -5020.00, tolerance 0.12); subtotal_matches_lines: sum of rows 65505.00 
    L06.pdf: scan_resolution: page is only 414px on its short side (< 800px, ~100 dpi)
    L07.pdf: totals_reconcile: line items 3550.00 + tax 334.13 = 3884.13 vs total 4384.13 (diff -500.00, tolerance 0.06); subtotal_matches_lines: sum of rows 3550.00 vs prin
    L09.pdf: scan_resolution: page is only 414px on its short side (< 800px, ~100 dpi)
    L10.pdf: totals_reconcile: line items 70300.00 + tax 19684.00 = 89984.00 vs total 90004.00 (diff -20.00, tolerance 0.07); scan_resolution: page is only 414px on its shor

COST
  model gemini-3.5-flash-lite | thinking=minimal | input mode=image | prompt v1
  docs that called the LLM: 10 | docs needing a 2nd round: 4
  avg tokens/doc: in 3,458 | out 983 | thinking 0
  avg cost/doc: $0.003494 | total for 10 docs: $0.03494
  avg latency/doc: 4.9s
  prices: https://ai.google.dev/gemini-api/docs/pricing (Standard tier, checked 2026-11-21)
```
