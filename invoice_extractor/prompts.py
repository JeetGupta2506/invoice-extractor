"""Prompt text. Bump PROMPT_VERSION whenever the wording changes: it is part of
the cache key, so a changed prompt never reuses old cached answers.

The extraction rules below restate the labelling conventions published in the
sample pack's README (vendor = seller at top, issue date not due date, discounts
are negative line items, tax_total = sum of tax lines, ...). They were written
from that spec, before looking at any model output.
"""

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """\
You extract data from business documents for an accounts-payable team.
You are given one document: an image of every page, and sometimes the text layer
extracted from the PDF. When both are present, use the image for layout (which
block is the seller, which column is which) and the text layer to read characters
and digits exactly. If they disagree, trust what is visible in the image.

STEP 1 - CLASSIFY
Set document_type. Use "invoice" only for an invoice / tax invoice / bill that a
seller issues to request payment for goods or services already supplied.
These are NOT invoices even though they contain amounts, line items or tax:
purchase orders, quotations / estimates, pro-forma invoices, bank or account
statements, receipts, delivery notes, letters, emails, CVs.
The document's own title (e.g. "PURCHASE ORDER", "Account Statement") is the
strongest signal. If the page is too damaged or blurred to read, use "unreadable".
If document_type is not "invoice", set every extraction field below to null.

STEP 2 - EXTRACT (invoices only)
- vendor: the seller / issuer name exactly as printed at the top of the document
  (letterhead, or the "From" block). Never the "Bill to" / customer.
- invoice_number: exactly as printed, keep slashes, dashes and leading zeros.
- invoice_date: the date the invoice was issued. Not the due date, PO date,
  order date or service period. Copy it verbatim into invoice_date_as_printed and
  give it as YYYY-MM-DD in invoice_date. For all-numeric dates like 07/02/2026,
  decide day-first vs month-first from the document's context (country of the
  addresses, currency, other dates on the page). US documents are usually
  month-first; Indian, UK and European documents are day-first.
- currency: ISO 4217 code inferred from symbols and context
  (Rs/INR/₹ -> INR, £ -> GBP, € -> EUR, $ -> USD unless the document clearly
  shows another dollar such as AUD, CAD or SGD).
- line_items: one entry per row of the item table, in printed order, across ALL
  pages. description exactly as printed. quantity = the number in the quantity
  column, or null if that cell is blank or "-". unit_price as printed or null.
  amount = the row's amount before tax. Charges (freight, shipping, service
  charge) and discounts that appear as rows of the item table are line items;
  a discount has a negative amount. Subtotal, tax and total rows are NOT line items.
- subtotal: as printed, or null if there is none.
- tax_lines: every tax line (GST, CGST, SGST, IGST, VAT, sales tax, MwSt, ...)
  with its label and amount. Empty list if the invoice has no tax line.
- tax_total: the sum of all tax lines; 0 if the invoice shows no tax or zero tax.
- total: the final amount payable including tax (Grand Total / Total /
  Amount due / Gesamtbetrag).

NUMBERS
Return plain JSON numbers: no currency symbols, no thousands separators.
Convert regional formats: "2,68,290.00" -> 268290.00 ; "1.029,00" -> 1029.00 ;
"6.080,00" -> 6080.00 ; "(450.00)" -> -450.00.
Copy every number exactly as printed. Do NOT correct the document's arithmetic:
if printed numbers do not add up, report them as printed and say so in notes.

OTHER
- legibility: "clear", "partly_legible" (some values were hard to read), or
  "illegible".
- notes: one or two short sentences about anything ambiguous or inconsistent;
  null if nothing.
"""

USER_PROMPT = "Extract the data from this document. Respond with JSON only."

TEXT_LAYER_HEADER = (
    "Text layer extracted from the PDF (reading order may be scrambled; "
    "use the images for layout):"
)


def retry_feedback(problems: list[str]) -> str:
    bullet_list = "\n".join(f"- {p}" for p in problems)
    return (
        "Your previous answer failed these automatic checks:\n"
        f"{bullet_list}\n"
        "Look at the document again carefully: check every line item amount, that no "
        "row was skipped or duplicated across pages, every tax line, and the final total. "
        "Then answer again with the full JSON. If the document's printed numbers really "
        "do not add up, keep them exactly as printed and explain in notes."
    )
