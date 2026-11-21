import pytest
from conftest import needs_samples

from invoice_extractor.matching import (FIELDS, compare, compare_line_items, match_amount,
                                        match_text, norm_vendor, parse_amount)


@pytest.mark.parametrize("raw,val", [
    (1200, 1200.0), ("1,200.00", 1200.0), ("₹ 2,68,290.00", 268290.0), ("1.029,00", 1029.0),
    ("€ 6.080,00", 6080.0), ("42,50", 42.5), ("(450.00)", -450.0), ("-450", -450.0), ("$4,384.13", 4384.13),
])
def test_parse_amount(raw, val):
    assert parse_amount(raw) == pytest.approx(val)


def test_brief_examples():
    assert match_amount("1,200.00", 1200)
    assert match_text("vendor", "Acme Pvt Ltd", "Acme")
    assert match_text("vendor", "ACME PVT. LTD.", "Acme Private Limited")


def test_vendor_rules():
    assert match_text("vendor", "Meridian Print and Pack LLP", "Meridian Print & Pack LLP")
    assert match_text("vendor", "Sakura Tea Traders BV", "Sakura Tea Traders B.V.")
    assert match_text("vendor", "COASTAL FRESH SEAFOODS", "Coastal Fresh Seafoods")
    assert not match_text("vendor", "Acme Supplies", "Acme")
    assert not match_text("vendor", "Rapid Cabs Pvt Ltd", "Metro Auto Parts")
    assert norm_vendor("Greenleaf Catering Co") == "greenleaf catering"


def test_invoice_number_rules():
    assert match_text("invoice_number", " kom/26-27/00418 ", "KOM/26-27/00418")
    assert match_text("invoice_number", "#PHS-1042", "PHS-1042")
    assert not match_text("invoice_number", "KOM/26-27/418", "KOM/26-27/00418")
    assert not match_text("invoice_number", "SGS1847", "SGS/1847")


def test_amount_tolerance_is_one_cent():
    assert match_amount(683.405, 683.4)
    assert not match_amount(683.42, 683.4)
    assert match_amount(None, None) and not match_amount(0, None)


def test_line_items():
    g = [{"description": "Pomfret, whole, kg", "quantity": 9.5, "amount": 6080.0},
         {"description": "Squid, cleaned, kg", "quantity": 7, "amount": 2870.0}]
    ok = [{"description": "Pomfret whole kg", "quantity": 9.5, "amount": 6080},
          {"description": "Squid, cleaned, kg", "quantity": 7.0, "amount": "2,870.00"}]
    assert compare_line_items(ok, g)["correct"]
    swapped = list(reversed(ok))
    assert not compare_line_items(swapped, g)["correct"]
    missing = ok[:1]
    r = compare_line_items(missing, g)
    assert not r["correct"] and r["rows_matched"] == 1
    wrong_qty = [dict(ok[0], quantity=None), ok[1]]
    assert not compare_line_items(wrong_qty, g)["correct"]


@needs_samples
def test_gold_matches_itself_and_none_scores_zero(gold):
    for g in gold.values():
        c = compare(g, g)
        assert all(c[f]["correct"] for f in FIELDS)
        c0 = compare(None, g)
        assert not any(c0[f]["correct"] for f in FIELDS)
