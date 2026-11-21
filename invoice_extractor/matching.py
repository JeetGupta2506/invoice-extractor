"""Field-by-field comparison of a prediction with ground truth.

Matching rules (also stated in REPORT.md):

  is_invoice      exact boolean.
  vendor          case-, punctuation- and whitespace-insensitive, "&" == "and",
                  and trailing legal suffixes ignored (Pvt, Ltd, LLP, Inc, GmbH,
                  B.V., Co, ...). So "Acme Pvt Ltd" == "ACME", but
                  "Acme Supplies" != "Acme". No fuzzy matching: a vendor name with
                  a wrong letter is wrong.
  invoice_number  exact after trimming, ignoring case, internal whitespace and a
                  leading "#". Slashes, dashes and zeros must match: "INV-041" != "INV-41".
  invoice_date    the same calendar date (both parsed as YYYY-MM-DD).
  currency        exact ISO code, case-insensitive.
  tax_total,      numerically equal within 0.01 (one cent/paisa). Strings such as
  total           "1,200.00", "₹1,200", "1.200,00" are parsed first, so
                  "1,200.00" == 1200.
  line_items      document is correct only if: same number of rows, every
                  ground-truth row is matched by a predicted row in the same
                  position with amount within 0.01, quantity equal (null == null,
                  else within 0.001) and description similarity >= 0.85 after
                  normalisation (difflib ratio, tolerates small OCR slips like a
                  dropped comma). Row-level precision/recall are reported too.

  null handling   null == null is correct (this is how a non-invoice scores on
                  the extraction fields). null vs a value is wrong either way.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Optional

AMOUNT_TOL = 0.01
QTY_TOL = 0.001
DESC_SIM_THRESHOLD = 0.85

FIELDS = ["is_invoice", "vendor", "invoice_number", "invoice_date", "currency",
          "line_items", "tax_total", "total"]

LEGAL_SUFFIXES = {
    "pvt", "private", "ltd", "limited", "llp", "llc", "inc", "incorporated", "corp",
    "corporation", "co", "company", "gmbh", "ag", "bv", "nv", "plc", "sa", "sarl",
    "srl", "pty", "pte", "ab", "oy", "as", "spa", "kg",
}


# ---------------------------------------------------------------- normalisers
def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold().replace("&", " and ")
    s = re.sub(r"[^\w\s]", " ", s)  # drop punctuation (B.V. -> b v)
    return re.sub(r"\s+", " ", s).strip()


def norm_vendor(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold().replace("&", " and ")
    s = re.sub(r"\b([a-z])\.(?=[a-z]\.)", r"\1", s)  # B.V. -> BV. before stripping punctuation
    s = s.replace(".", "")
    tokens = re.sub(r"[^\w\s]", " ", s).split()
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def norm_invoice_number(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).strip().casefold()
    s = re.sub(r"\s+", "", s)
    return s.lstrip("#")


def parse_amount(v: Any) -> Optional[float]:
    """1200 / 1200.0 / "1,200.00" / "₹ 2,68,290.00" / "1.029,00" / "(450.00)" -> float."""
    if v is None:
        return None
    if isinstance(v, bool):
        raise ValueError("boolean is not an amount")
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    neg = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[^\d,.\-]", "", s)
    if not s:
        return None
    if "," in s and "." in s:
        # whichever separator comes last is the decimal point
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # "1,029" (thousands) vs "42,50" (decimal comma): 3 digits after = thousands
        head, _, tail = s.rpartition(",")
        s = s.replace(",", "") if len(tail) == 3 else head.replace(",", "") + "." + tail
    x = float(s)
    return -abs(x) if neg else x


def parse_date(v: Any) -> Optional[dt.date]:
    if v is None:
        return None
    try:
        return dt.date.fromisoformat(str(v).strip())
    except ValueError:
        return None


# ---------------------------------------------------------------- comparators
def _both_none(a, b) -> Optional[bool]:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return None


def match_text(field: str, pred, gold) -> bool:
    r = _both_none(pred, gold)
    if r is not None:
        return r
    if field == "vendor":
        return norm_vendor(pred) == norm_vendor(gold)
    if field == "invoice_number":
        return norm_invoice_number(pred) == norm_invoice_number(gold)
    if field == "currency":
        return str(pred).strip().upper() == str(gold).strip().upper()
    raise KeyError(field)


def match_amount(pred, gold) -> bool:
    r = _both_none(pred, gold)
    if r is not None:
        return r
    try:
        p, g = parse_amount(pred), parse_amount(gold)
    except ValueError:
        return False
    if p is None or g is None:
        return p is None and g is None
    return abs(p - g) <= AMOUNT_TOL + 1e-9


def match_quantity(pred, gold) -> bool:
    r = _both_none(pred, gold)
    if r is not None:
        return r
    try:
        return abs(parse_amount(pred) - parse_amount(gold)) <= QTY_TOL
    except (TypeError, ValueError):
        return False


def desc_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, norm_text(a), norm_text(b)).ratio()


def compare_line_items(pred, gold) -> dict:
    """Row-level comparison. Positional alignment (row order is part of the spec)."""
    r = _both_none(pred, gold)
    if r is not None:
        n_gold = len(gold or [])
        n_pred = len(pred or [])
        return {"correct": r, "n_gold": n_gold, "n_pred": n_pred, "rows_matched": 0,
                "rows": [], "issues": [] if r else ["one side is null"]}

    rows, issues = [], []
    matched = 0
    for i in range(max(len(pred), len(gold))):
        g = gold[i] if i < len(gold) else None
        p = pred[i] if i < len(pred) else None
        if g is None:
            issues.append(f"row {i+1}: extra predicted row {p.get('description')!r} {p.get('amount')}")
            rows.append({"row": i + 1, "ok": False, "why": "extra"})
            continue
        if p is None:
            issues.append(f"row {i+1}: missing row {g['description']!r} {g['amount']}")
            rows.append({"row": i + 1, "ok": False, "why": "missing"})
            continue
        amt = match_amount(p.get("amount"), g["amount"])
        qty = match_quantity(p.get("quantity"), g["quantity"])
        sim = desc_similarity(str(p.get("description", "")), g["description"])
        desc = sim >= DESC_SIM_THRESHOLD
        ok = amt and qty and desc
        matched += ok
        why = []
        if not amt:
            why.append(f"amount {p.get('amount')} != {g['amount']}")
        if not qty:
            why.append(f"quantity {p.get('quantity')} != {g['quantity']}")
        if not desc:
            why.append(f"description {p.get('description')!r} vs {g['description']!r} (sim {sim:.2f})")
        if why:
            issues.append(f"row {i+1}: " + "; ".join(why))
        rows.append({"row": i + 1, "ok": ok, "amount_ok": amt, "quantity_ok": qty,
                     "description_ok": desc, "description_sim": round(sim, 3)})

    correct = len(pred) == len(gold) and matched == len(gold)
    return {"correct": correct, "n_gold": len(gold), "n_pred": len(pred),
            "rows_matched": matched, "rows": rows, "issues": issues}


def compare(pred: Optional[dict], gold: dict) -> dict:
    """Returns {field: {"correct": bool, "pred": ..., "gold": ..., ...}}.
    A missing prediction (pipeline failed/rejected) counts as wrong on every field."""
    out = {}
    if pred is None:
        for f in FIELDS:
            out[f] = {"correct": False, "pred": None, "gold": gold.get(f), "why": "no prediction"}
        out["line_items"].update({"n_gold": len(gold.get("line_items") or []), "n_pred": 0, "rows_matched": 0})
        return out

    out["is_invoice"] = {"correct": pred.get("is_invoice") is gold["is_invoice"]}
    for f in ("vendor", "invoice_number", "currency"):
        out[f] = {"correct": match_text(f, pred.get(f), gold[f])}
    pd_, gd = pred.get("invoice_date"), gold["invoice_date"]
    out["invoice_date"] = {"correct": (pd_ is None and gd is None) or
                           (parse_date(pd_) is not None and parse_date(pd_) == parse_date(gd))}
    for f in ("tax_total", "total"):
        out[f] = {"correct": match_amount(pred.get(f), gold[f])}
    out["line_items"] = compare_line_items(pred.get("line_items"), gold["line_items"])

    for f in FIELDS:
        if f != "line_items":
            out[f].update({"pred": pred.get(f), "gold": gold[f]})
    return out
