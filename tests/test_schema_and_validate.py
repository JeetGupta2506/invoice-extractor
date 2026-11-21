import copy

import pytest
from conftest import needs_samples

from invoice_extractor.schema import LLMExtraction, to_result
from invoice_extractor.validate import check_schema, check_totals, failed, run_checks


def _ext(**over):
    base = dict(
        document_type="invoice", legibility="clear", vendor="Acme Supplies Pvt Ltd",
        invoice_number="INV-2041", invoice_date_as_printed="14 Mar 2026", invoice_date="2026-03-14",
        currency="INR",
        line_items=[{"description": "A4 paper", "quantity": 10, "unit_price": 320.0, "amount": 3200.0}],
        subtotal=3200.0, tax_lines=[{"label": "CGST 9%", "amount": 288.0}, {"label": "SGST 9%", "amount": 288.0}],
        tax_total=576.0, total=3776.0, notes=None,
    )
    base.update(over)
    return LLMExtraction.model_validate(base)


@needs_samples
def test_ground_truth_passes_schema_and_totals(gold):
    """Sanity check of our own validator: every label must pass it."""
    assert len(gold) == 10
    for name, g in gold.items():
        assert all(c.passed for c in check_schema(g)), name
        t = check_totals(g)
        assert t is None or t.passed, (name, t.detail)


def test_brief_example_is_valid():
    r = to_result(_ext())
    checks = run_checks(_ext(), r)
    assert not failed(checks), [c.detail for c in failed(checks)]
    assert r["tax_total"] == 576.0 and r["line_items"][0]["quantity"] == 10


def test_totals_mismatch_is_an_error():
    e = _ext(total=3900.0)
    errs = failed(run_checks(e, to_result(e)), "error")
    assert [c.name for c in errs] == ["totals_reconcile"]


def test_rounding_tolerance():
    e = _ext(total=3776.02)  # within 0.01 * (1 + 2)
    assert not failed(run_checks(e, to_result(e)), "error")


def test_non_invoice_projects_to_nulls():
    e = _ext(document_type="purchase_order")
    r = to_result(e)
    assert r["is_invoice"] is False and all(v is None for k, v in r.items() if k != "is_invoice")
    assert not failed(run_checks(e, r), "error")


def test_non_invoice_with_fields_fails_schema():
    bad = {"is_invoice": False, "vendor": "X", "invoice_number": None, "invoice_date": None,
           "currency": None, "line_items": None, "tax_total": None, "total": None}
    names = {c.name for c in check_schema(bad) if not c.passed}
    assert names == {"schema_pydantic", "schema_json"}


@pytest.mark.parametrize("field,value", [("invoice_date", "14/03/2026"), ("currency", "Rs"),
                                         ("invoice_date", "2026-02-30")])
def test_bad_formats_fail_schema(field, value):
    e = _ext(**{field: value})
    errs = failed(run_checks(e, to_result(e)), "error")
    assert errs and errs[0].name.startswith("schema")


def test_tax_total_is_sum_of_tax_lines():
    e = _ext(tax_total=999.0)  # model's own sum is wrong; we recompute from the lines
    r = to_result(e)
    assert r["tax_total"] == 576.0
    warn = {c.name for c in failed(run_checks(e, r), "warning")}
    assert "tax_lines_sum" in warn


def test_no_tax_means_zero():
    e = _ext(tax_lines=[], tax_total=None, total=3200.0)
    assert to_result(e)["tax_total"] == 0.0


def test_line_math_allows_rounded_unit_price():
    # U04: 1440 x 0.09 = 129.60 but the row says 122.40. That is consistent with a true
    # rate of 0.085 printed rounded to 0.09 (1440 x 0.085 = 122.40), so it is NOT an error.
    items = [{"description": "Compute", "quantity": 1440, "unit_price": 0.09, "amount": 122.40}]
    e = _ext(line_items=items, subtotal=122.40, tax_lines=[], tax_total=0, total=122.40)
    assert "line_math" not in {c.name for c in failed(run_checks(e, to_result(e)))}


def test_line_math_catches_inconsistent_row():
    items = [{"description": "Compute", "quantity": 1440, "unit_price": 0.09, "amount": 112.40}]
    e = _ext(line_items=items, subtotal=112.40, tax_lines=[], tax_total=0, total=112.40)
    assert "line_math" in {c.name for c in failed(run_checks(e, to_result(e)), "warning")}


def test_line_math_tolerance_is_rounding_based():
    # stress-test case: quantity misread 18 -> 20, unit price 780 -> 700, amount 14040 read right
    items = [{"description": "Prawns", "quantity": 20, "unit_price": 700.0, "amount": 14040.0}]
    e = _ext(line_items=items, subtotal=14040.0, tax_lines=[], tax_total=0, total=14040.0)
    assert "line_math" in {c.name for c in failed(run_checks(e, to_result(e)), "warning")}
    # genuine rounding: 3 x 33.33 = 99.99 printed as 100.00 is NOT flagged... but 0.01 off only
    ok = [{"description": "X", "quantity": 12.5, "unit_price": 920.0, "amount": 11500.0},
          {"description": "Y", "quantity": 3, "unit_price": 33.33, "amount": 99.99}]
    e2 = _ext(line_items=ok, subtotal=11599.99, tax_lines=[], tax_total=0, total=11599.99)
    assert "line_math" not in {c.name for c in failed(run_checks(e2, to_result(e2)))}


def test_scan_resolution_check():
    from invoice_extractor.validate import check_resolution
    assert check_resolution("pdf_digital", [(400, 600)]) is None
    assert not check_resolution("pdf_scanned", [(414, 585)]).passed
    assert check_resolution("image", [(1050, 1449)]).passed


def test_ambiguous_date_warning():
    e = _ext(invoice_date_as_printed="07/02/2026", invoice_date="2026-02-07")
    warn = {c.name for c in failed(run_checks(e, to_result(e)), "warning")}
    assert "date_unambiguous" in warn
    e2 = _ext(invoice_date_as_printed="23/06/2026", invoice_date="2026-06-23")
    assert "date_unambiguous" not in {c.name for c in failed(run_checks(e2, to_result(e2)))}


def test_discount_row_negative_amount_reconciles():
    items = [{"description": "Work", "quantity": 1, "unit_price": 500, "amount": 500.0},
             {"description": "Discount", "quantity": None, "unit_price": None, "amount": -50.0}]
    e = _ext(line_items=items, subtotal=450.0, tax_lines=[], tax_total=0, total=450.0)
    assert not failed(run_checks(e, to_result(e)), "error")


def test_result_does_not_mutate_extraction():
    e = _ext()
    before = copy.deepcopy(e.model_dump())
    to_result(e)
    assert e.model_dump() == before
