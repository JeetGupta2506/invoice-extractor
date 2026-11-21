"""Data models.

Two layers:

* ``InvoiceResult`` is the *output contract*: exactly the fields in the
  assignment's ``schema.json`` and nothing else (``extra="forbid"``).
* ``LLMExtraction`` is what we ask the model to fill in. It is a superset:
  it also asks for the subtotal, unit prices, each tax line separately, the
  date exactly as printed, and a document type. We never return those extra
  fields, but the validator uses them to cross-check the answer
  (e.g. qty x unit price == amount, sum of tax lines == tax total).
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Number = Union[int, float]  # smart union: keeps 3 as 3 and 3.5 as 3.5

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")


# --------------------------------------------------------------------------
# Output contract (mirrors schema.json)
# --------------------------------------------------------------------------
class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    quantity: Optional[Number]
    amount: Number


class InvoiceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_invoice: bool
    vendor: Optional[str]
    invoice_number: Optional[str]
    invoice_date: Optional[str]
    currency: Optional[str]
    line_items: Optional[list[LineItem]]
    tax_total: Optional[Number]
    total: Optional[Number]

    @field_validator("invoice_date")
    @classmethod
    def _iso_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not _ISO_DATE.match(v):
            raise ValueError(f"invoice_date must be YYYY-MM-DD, got {v!r}")
        dt.date.fromisoformat(v)  # rejects 2026-02-30 etc.
        return v

    @field_validator("currency")
    @classmethod
    def _iso_currency(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not _CURRENCY.match(v):
            raise ValueError(f"currency must be a 3-letter ISO 4217 code, got {v!r}")
        return v

    @model_validator(mode="after")
    def _non_invoice_is_all_null(self) -> "InvoiceResult":
        if not self.is_invoice:
            filled = [
                name
                for name in ("vendor", "invoice_number", "invoice_date", "currency",
                             "line_items", "tax_total", "total")
                if getattr(self, name) is not None
            ]
            if filled:
                raise ValueError(f"is_invoice is false but these fields are not null: {filled}")
        return self


# --------------------------------------------------------------------------
# What the LLM fills in (richer, used for cross-checks)
# --------------------------------------------------------------------------
DocumentType = Literal[
    "invoice",
    "purchase_order",
    "quotation",
    "bank_statement",
    "receipt",
    "delivery_note",
    "letter",
    "other",
    "unreadable",
]


class LLMLineItem(BaseModel):
    description: str = Field(description="Row description exactly as printed.")
    quantity: Optional[float] = Field(description="Quantity as printed; null if the row has no quantity (blank or '-').")
    unit_price: Optional[float] = Field(description="Unit price / rate as printed; null if not shown.")
    amount: float = Field(description="Row amount before tax. Discounts are negative.")


class LLMTaxLine(BaseModel):
    label: str = Field(description="Tax line label as printed, e.g. 'CGST @ 9%', 'VAT @ 20%'.")
    amount: float


class LLMExtraction(BaseModel):
    document_type: DocumentType = Field(description="What kind of document this is. Only 'invoice' counts as an invoice.")
    legibility: Literal["clear", "partly_legible", "illegible"] = Field(
        description="How readable the document is. Use partly_legible if any number you report was hard to read."
    )
    vendor: Optional[str] = Field(description="Seller / issuer name as printed at the top. Never the bill-to customer.")
    invoice_number: Optional[str]
    invoice_date_as_printed: Optional[str] = Field(description="The issue date copied verbatim from the document.")
    invoice_date: Optional[str] = Field(description="The issue date as YYYY-MM-DD.")
    currency: Optional[str] = Field(description="ISO 4217 code, e.g. INR, USD, EUR, GBP.")
    line_items: Optional[list[LLMLineItem]]
    subtotal: Optional[float] = Field(description="Subtotal as printed, or null if not shown.")
    tax_lines: Optional[list[LLMTaxLine]] = Field(description="Every tax line printed on the invoice. Empty list if none.")
    tax_total: Optional[float] = Field(description="Sum of all tax lines; 0 if the invoice shows no tax.")
    total: Optional[float] = Field(description="Final amount payable including tax.")
    notes: Optional[str] = Field(description="Short note on anything ambiguous or inconsistent. Null if nothing.")

    @property
    def is_invoice(self) -> bool:
        return self.document_type == "invoice"


def _clean_number(x: Optional[float]) -> Optional[float]:
    """Round money to cents (sums of floats like 1016.25 + 1016.25 can drift)."""
    if x is None:
        return None
    x = round(float(x), 2)
    return 0.0 if x == 0 else x  # avoid -0.0


def _clean_quantity(q: Optional[float]) -> Optional[Number]:
    if q is None:
        return None
    q = round(float(q), 4)
    return int(q) if q.is_integer() else q


def to_result(ext: LLMExtraction) -> dict:
    """Project the rich LLM answer onto the output contract (a plain dict).

    Deterministic bits done in code rather than trusted to the model:
      * is_invoice is derived from document_type (one source of truth)
      * non-invoices get every other field set to null
      * tax_total is the sum of the individual tax lines when the model listed them
      * amounts rounded to cents, integral quantities written as ints
    """
    if not ext.is_invoice:
        return {
            "is_invoice": False,
            "vendor": None,
            "invoice_number": None,
            "invoice_date": None,
            "currency": None,
            "line_items": None,
            "tax_total": None,
            "total": None,
        }

    if ext.tax_lines:
        tax_total = sum(t.amount for t in ext.tax_lines)
    elif ext.tax_total is not None:
        tax_total = ext.tax_total
    else:
        tax_total = 0.0  # labelling rule 5: no tax shown -> 0

    return {
        "is_invoice": True,
        "vendor": (ext.vendor or "").strip() or None,
        "invoice_number": (ext.invoice_number or "").strip() or None,
        "invoice_date": ext.invoice_date,
        "currency": ext.currency.strip().upper() if ext.currency else None,
        "line_items": [
            {
                "description": li.description.strip(),
                "quantity": _clean_quantity(li.quantity),
                "amount": _clean_number(li.amount),
            }
            for li in (ext.line_items or [])
        ],
        "tax_total": _clean_number(tax_total),
        "total": _clean_number(ext.total),
    }
