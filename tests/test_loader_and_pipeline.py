import io
import json

import pytest
from conftest import LABELLED, needs_samples
from PIL import Image

from invoice_extractor.llm import LLMError, LLMResponse
from invoice_extractor.loader import DocumentError, load_document
from invoice_extractor.pipeline import extract_document


# ------------------------------------------------------------------ loader
def _img_bytes(color="white", size=(800, 1100), fmt="PNG", draw_text=False):
    img = Image.new("RGB", size, color)
    if draw_text:
        from PIL import ImageDraw
        d = ImageDraw.Draw(img)
        for y in range(50, 1000, 40):
            d.text((50, y), "INVOICE 12345  Widget  10 x 2.00 = 20.00", fill="black")
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


@pytest.mark.parametrize("name,content,code", [
    ("empty.pdf", b"", "empty_file"),
    ("notes.pdf", b"this is a text file pretending to be a pdf\n" * 10, "unsupported_type"),
    ("truncated.pdf", b"%PDF-1.7\n1 0 obj << /Type /Catalog >>\n", "corrupt_pdf"),
    ("broken.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 200, "corrupt_image"),
])
def test_bad_inputs_rejected(tmp_path, name, content, code):
    p = tmp_path / name
    p.write_bytes(content)
    with pytest.raises(DocumentError) as e:
        load_document(p)
    assert e.value.code == code


def test_missing_file(tmp_path):
    with pytest.raises(DocumentError) as e:
        load_document(tmp_path / "nope.pdf")
    assert e.value.code == "file_not_found"


def test_blank_image_rejected(tmp_path):
    p = tmp_path / "blank.png"
    p.write_bytes(_img_bytes())
    with pytest.raises(DocumentError) as e:
        load_document(p)
    assert e.value.code == "blank_document"


def test_image_with_content_loads(tmp_path):
    p = tmp_path / "scan.png"
    p.write_bytes(_img_bytes(draw_text=True))
    doc = load_document(p)
    assert doc.source_kind == "image" and doc.page_count == 1 and doc.pages[0].mime_type == "image/jpeg"


@needs_samples
@pytest.mark.parametrize("name,kind,pages", [
    ("L01.pdf", "pdf_digital", 1), ("L04.pdf", "pdf_digital", 2),
    ("L09.pdf", "pdf_scanned", 1), ("L02.jpg", "image", 1),
])
def test_sample_kinds(name, kind, pages):
    doc = load_document(LABELLED / name)
    assert doc.source_kind == kind and doc.page_count == pages
    assert (doc.text_layer is not None) == (kind == "pdf_digital")


# ------------------------------------------------------------------ pipeline with a fake LLM
GOOD = {
    "document_type": "invoice", "legibility": "clear", "vendor": "Acme", "invoice_number": "1",
    "invoice_date_as_printed": "14 March 2026", "invoice_date": "2026-03-14", "currency": "USD",
    "line_items": [{"description": "Thing", "quantity": 2, "unit_price": 50, "amount": 100}],
    "subtotal": 100, "tax_lines": [{"label": "Tax", "amount": 10}], "tax_total": 10, "total": 110, "notes": None,
}


class FakeClient:
    model = "gemini-3.5-flash-lite"
    thinking_level = "minimal"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def generate(self, doc, system_prompt, conversation, response_schema, input_mode):
        self.calls.append(list(conversation))
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        text = r if isinstance(r, str) else json.dumps(r)
        return LLMResponse(text=text, model=self.model, input_tokens=1000, output_tokens=200,
                           thinking_tokens=0, latency_s=0.1)


@pytest.fixture
def doc_path(tmp_path):
    p = tmp_path / "inv.png"
    p.write_bytes(_img_bytes(draw_text=True))
    return p


def test_ok(doc_path):
    o = extract_document(doc_path, FakeClient([GOOD]))
    assert o.status == "ok" and o.result["total"] == 110 and not o.needs_review
    assert o.llm["cost_usd"] == pytest.approx(1000 * 0.30 / 1e6 + 200 * 2.50 / 1e6)


def test_retry_fixes_totals(doc_path):
    bad = dict(GOOD, total=999)
    fake = FakeClient([bad, GOOD])
    o = extract_document(doc_path, fake)
    assert o.status == "ok_after_retry" and o.result["total"] == 110
    assert "totals_reconcile" in fake.calls[1][-1]  # feedback names the failed check
    assert o.llm["input_tokens"] == 2000  # both rounds are billed


def test_still_wrong_after_retry_is_flagged_not_hidden(doc_path):
    bad = dict(GOOD, total=999)
    o = extract_document(doc_path, FakeClient([bad, bad]))
    assert o.status == "flagged" and o.needs_review
    assert o.result is not None and any("totals_reconcile" in r for r in o.review_reasons)


def test_invalid_json_twice_fails(doc_path):
    o = extract_document(doc_path, FakeClient(["not json", "{\"also\": \"wrong\"}"]))
    assert o.status == "failed" and o.result is None and o.error["code"] == "invalid_llm_output"


def test_garbled_retry_keeps_first_usable_answer(doc_path):
    o = extract_document(doc_path, FakeClient([dict(GOOD, total=999), "garbage"]))
    assert o.status == "flagged" and o.result["total"] == 999


def test_timeout_is_reported(doc_path):
    o = extract_document(doc_path, FakeClient([LLMError("timeout", "no response in 90s", retryable=True)]))
    assert o.status == "failed" and o.error["code"] == "timeout" and o.result is None


def test_non_invoice(doc_path):
    reply = {k: None for k in GOOD}
    reply.update(document_type="bank_statement", legibility="clear")
    o = extract_document(doc_path, FakeClient([reply]))
    assert o.status == "ok" and o.result["is_invoice"] is False and o.result["vendor"] is None


def test_rejected_input_never_calls_llm(tmp_path):
    p = tmp_path / "empty.pdf"
    p.write_bytes(b"")
    fake = FakeClient([])
    o = extract_document(p, fake)
    assert o.status == "rejected" and o.error["code"] == "empty_file" and fake.calls == []
