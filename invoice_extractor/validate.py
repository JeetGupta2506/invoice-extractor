"""Checks run on every extraction.

Severity:
  error   -> the answer is wrong or unusable as-is. The pipeline retries once
             with the failures fed back to the model; if it still fails, the
             document is returned with status "flagged" and needs_review=true.
  warning -> the answer may be fine but a human should look (needs_review=true).
             No retry: a retry costs money and these are often genuine
             properties of the document (e.g. an ambiguous 07/02 date).

Nothing is ever silently passed on: every result carries its check list.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import asdict, dataclass
from importlib import resources
from typing import Optional

import jsonschema
from pydantic import ValidationError

from .schema import InvoiceResult, LLMExtraction

# Common ISO 4217 codes. Anything else is a warning, not an error.
KNOWN_CURRENCIES = {
    "INR", "USD", "EUR", "GBP", "JPY", "CNY", "AUD", "CAD", "SGD", "AED", "CHF", "HKD",
    "NZD", "SEK", "NOK", "DKK", "ZAR", "SAR", "MYR", "THB", "IDR", "PHP", "KRW", "BRL",
    "MXN", "PLN", "CZK", "HUF", "TRY", "LKR", "NPR", "BDT", "PKR", "QAR", "KWD", "BHD", "OMR",
}

_OUTPUT_SCHEMA = json.loads(
    resources.files("invoice_extractor").joinpath("output_schema.json").read_text(encoding="utf-8")
)


@dataclass
class Check:
    name: str
    passed: bool
    severity: str  # "error" | "warning"
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def totals_tolerance(n_line_items: int) -> float:
    """Each printed value is rounded to 0.01, so each can be off by up to 0.005.
    Allow one cent per value in the sum (line items + tax + total)."""
    return 0.01 * (n_line_items + 2)


def _close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol + 1e-9


def check_schema(result: dict) -> list[Check]:
    checks = []
    try:
        InvoiceResult.model_validate(result)
        checks.append(Check("schema_pydantic", True, "error"))
    except ValidationError as e:
        msg = "; ".join(f"{'.'.join(map(str, er['loc']))}: {er['msg']}" for er in e.errors())
        checks.append(Check("schema_pydantic", False, "error", msg))
    errs = sorted(jsonschema.Draft202012Validator(_OUTPUT_SCHEMA).iter_errors(result), key=str)
    checks.append(Check(
        "schema_json", not errs, "error",
        "; ".join(f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in errs[:5]),
    ))
    return checks


def check_totals(result: dict) -> Optional[Check]:
    """Sum of line item amounts + tax_total == total (the check the brief asks for)."""
    if not result.get("is_invoice"):
        return None
    items = result.get("line_items") or []
    total, tax = result.get("total"), result.get("tax_total")
    if total is None or not items:
        return Check("totals_reconcile", False, "error",
                     f"cannot reconcile: total={total}, {len(items)} line items")
    lines = sum(li["amount"] for li in items)
    expected = lines + (tax or 0)
    tol = totals_tolerance(len(items))
    ok = _close(expected, total, tol)
    return Check(
        "totals_reconcile", ok, "error",
        f"line items {lines:.2f} + tax {tax or 0:.2f} = {expected:.2f} vs total {total:.2f} "
        f"(diff {expected - total:+.2f}, tolerance {tol:.2f})",
    )


def run_checks(ext: Optional[LLMExtraction], result: dict, today: Optional[dt.date] = None) -> list[Check]:
    today = today or dt.date.today()
    checks = check_schema(result)
    if not all(c.passed for c in checks):
        return checks  # nothing else is meaningful on a malformed result

    if ext is not None and ext.document_type == "unreadable":
        checks.append(Check("readable", False, "error", "model reported the document as unreadable"))
        return checks

    if not result["is_invoice"]:
        # nothing more to check for non-invoices; record what the model thought it was
        checks.append(Check("classified_non_invoice", True, "warning",
                            f"document_type={ext.document_type if ext else '?'}"))
        return checks

    t = check_totals(result)
    if t:
        checks.append(t)

    # required fields for a usable invoice
    missing = [f for f in ("vendor", "invoice_number", "invoice_date", "currency", "total")
               if result.get(f) in (None, "")]
    checks.append(Check("required_fields", not missing, "error",
                        f"missing: {', '.join(missing)}" if missing else ""))

    if ext is not None:
        items = ext.line_items or []
        # subtotal printed on the document should equal the sum of the rows
        if ext.subtotal is not None and items:
            s = sum(li.amount for li in items)
            checks.append(Check("subtotal_matches_lines",
                                _close(s, ext.subtotal, totals_tolerance(len(items))), "warning",
                                f"sum of rows {s:.2f} vs printed subtotal {ext.subtotal:.2f}"))

        # tax lines vs the model's own tax_total
        if ext.tax_lines and ext.tax_total is not None:
            s = sum(t.amount for t in ext.tax_lines)
            checks.append(Check("tax_lines_sum", _close(s, ext.tax_total, 0.01 * (len(ext.tax_lines) + 1)),
                                "warning", f"tax lines {s:.2f} vs tax_total {ext.tax_total:.2f}"))

        # quantity x unit price == amount, per row. The unit price is printed to the
        # cent, so it can be off by 0.005; times the quantity, plus a cent for the amount.
        # (v1 used 0.5% of the amount: too loose, it let 20 x 700 = 14040 through.)
        bad_rows = []
        for i, li in enumerate(items, start=1):
            if li.quantity is not None and li.unit_price is not None:
                exp = li.quantity * li.unit_price
                if not _close(exp, li.amount, 0.01 + abs(li.quantity) * 0.005):
                    bad_rows.append(f"row {i}: {li.quantity:g} x {li.unit_price:g} = {exp:.2f} but amount is {li.amount:.2f}")
        if items:
            checks.append(Check("line_math", not bad_rows, "warning", "; ".join(bad_rows)))

        # ambiguous all-numeric date (both parts <= 12): day/month order was a judgement call
        raw = ext.invoice_date_as_printed or ""
        m = re.fullmatch(r"\s*(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\s*", raw)
        if m and int(m.group(1)) <= 12 and int(m.group(2)) <= 12 and m.group(1) != m.group(2):
            checks.append(Check("date_unambiguous", False, "warning",
                                f"'{raw}' could be day-first or month-first; read as {result['invoice_date']}"))

        if ext.legibility != "clear":
            checks.append(Check("legibility", False, "warning", f"model reported legibility={ext.legibility}"))

    if result.get("invoice_date"):
        d = dt.date.fromisoformat(result["invoice_date"])
        ok = dt.date(2000, 1, 1) <= d <= today + dt.timedelta(days=31)
        checks.append(Check("date_plausible", ok, "warning", "" if ok else f"{d} is outside 2000-01-01..today+31d"))

    cur = result.get("currency")
    if cur:
        checks.append(Check("currency_known", cur in KNOWN_CURRENCIES, "warning",
                            "" if cur in KNOWN_CURRENCIES else f"uncommon currency code {cur}"))

    if result.get("total") is not None and result["total"] <= 0:
        checks.append(Check("total_positive", False, "warning", f"total is {result['total']}"))

    return checks


MIN_SCAN_SIDE_PX = 800  # ~100 dpi on an A4 / Letter page


def check_resolution(source_kind: str, page_sizes: list[tuple[int, int]]) -> Optional[Check]:
    """Warn when a scan/photo is too small to read small print reliably.

    The stress test showed that below ~100 dpi the model does not just fail, it
    produces plausible, internally consistent numbers (so the totals check passes)
    while still rating legibility "clear". Pixel count is a signal the model cannot
    talk its way around. Digital PDFs are exempt: their text layer carries the digits.
    """
    if source_kind == "pdf_digital" or not page_sizes:
        return None
    smallest = min(min(w, h) for w, h in page_sizes)
    ok = smallest >= MIN_SCAN_SIDE_PX
    return Check("scan_resolution", ok, "warning",
                 "" if ok else f"page is only {smallest}px on its short side (< {MIN_SCAN_SIDE_PX}px, ~100 dpi)")


def failed(checks: list[Check], severity: Optional[str] = None) -> list[Check]:
    return [c for c in checks if not c.passed and (severity is None or c.severity == severity)]
