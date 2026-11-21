"""Turn a file on disk into page images (+ the PDF text layer when there is one).

This is also where the "bad input" handling lives. Anything we can reject
*before* paying for an LLM call is rejected here with a ``DocumentError``
carrying a machine-readable code:

    file_not_found, empty_file, file_too_large, unsupported_type,
    corrupt_pdf, encrypted_pdf, corrupt_image, too_many_pages, blank_document

The file type is detected from the file's first bytes (its "magic number"),
not from its extension, so a text file renamed to .pdf is caught.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pymupdf
from PIL import Image, ImageOps, ImageStat, UnidentifiedImageError

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_PAGES = 10
PDF_RENDER_DPI = 150          # A4 -> ~1240x1754 px: small text stays readable
MAX_IMAGE_SIDE = 2000         # downscale big phone photos; more pixels != more accuracy
MIN_TEXT_LAYER_CHARS = 40     # below this we treat a PDF page set as scanned
BLANK_STDDEV_THRESHOLD = 4.0  # grayscale std-dev of a near-uniform (blank) page

Image.MAX_IMAGE_PIXELS = 60_000_000  # guard against decompression bombs


class DocumentError(Exception):
    """The input cannot be processed. ``code`` is stable and machine-readable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


@dataclass
class PageImage:
    data: bytes
    mime_type: str
    width: int
    height: int


@dataclass
class LoadedDocument:
    path: Path
    source_kind: str                 # "pdf_digital" | "pdf_scanned" | "image"
    pages: list[PageImage] = field(default_factory=list)
    text_layer: Optional[str] = None  # None for scans / photos
    file_bytes: bytes = b""

    @property
    def page_count(self) -> int:
        return len(self.pages)


def _sniff(head: bytes) -> str:
    if head.startswith(b"%PDF-") or b"%PDF-" in head[:1024]:
        return "pdf"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "webp"
    return "unknown"


def _is_blank(img: Image.Image) -> bool:
    gray = img.convert("L")
    gray.thumbnail((400, 400))
    return ImageStat.Stat(gray).stddev[0] < BLANK_STDDEV_THRESHOLD


def _load_pdf(path: Path, data: bytes) -> LoadedDocument:
    try:
        pdf = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:  # pymupdf raises several types for broken files
        raise DocumentError("corrupt_pdf", f"Could not open PDF: {e}") from e

    with pdf:
        if pdf.needs_pass:
            raise DocumentError("encrypted_pdf", "PDF is password-protected.")
        if pdf.page_count == 0:
            raise DocumentError("corrupt_pdf", "PDF has no pages.")
        if pdf.page_count > MAX_PAGES:
            raise DocumentError(
                "too_many_pages",
                f"PDF has {pdf.page_count} pages; limit is {MAX_PAGES}. "
                "Long documents are usually not single invoices; route to a human.",
            )

        pages: list[PageImage] = []
        texts: list[str] = []
        text_chars = 0
        blank_pages = 0
        try:
            for i, page in enumerate(pdf, start=1):
                pix = page.get_pixmap(dpi=PDF_RENDER_DPI)
                png = pix.tobytes("png")
                img = Image.open(io.BytesIO(png))
                if _is_blank(img):
                    blank_pages += 1
                pages.append(PageImage(png, "image/png", pix.width, pix.height))
                page_text = page.get_text().strip()
                text_chars += len(page_text)
                texts.append(f"--- page {i} ---\n{page_text}")
        except DocumentError:
            raise
        except Exception as e:
            raise DocumentError("corrupt_pdf", f"Failed to render PDF page: {e}") from e

    if blank_pages == len(pages):
        raise DocumentError("blank_document", "Every page is blank; nothing to extract.")

    text = "\n".join(texts)
    has_text = text_chars >= MIN_TEXT_LAYER_CHARS
    return LoadedDocument(
        path=path,
        source_kind="pdf_digital" if has_text else "pdf_scanned",
        pages=pages,
        text_layer=text if has_text else None,
        file_bytes=data,
    )


def _load_image(path: Path, data: bytes) -> LoadedDocument:
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()  # catches truncated / corrupt files
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as e:
        raise DocumentError("corrupt_image", f"Could not decode image: {e}") from e

    img = ImageOps.exif_transpose(img)  # phone photos often store rotation in EXIF
    img = img.convert("RGB")
    if _is_blank(img):
        raise DocumentError("blank_document", "Image is blank; nothing to extract.")
    img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return LoadedDocument(
        path=path,
        source_kind="image",
        pages=[PageImage(buf.getvalue(), "image/jpeg", img.width, img.height)],
        text_layer=None,
        file_bytes=data,
    )


def load_document(path: str | Path) -> LoadedDocument:
    path = Path(path)
    if not path.is_file():
        raise DocumentError("file_not_found", f"No such file: {path}")

    size = path.stat().st_size
    if size == 0:
        raise DocumentError("empty_file", "File is empty (0 bytes).")
    if size > MAX_FILE_BYTES:
        raise DocumentError("file_too_large", f"File is {size/1e6:.1f} MB; limit is {MAX_FILE_BYTES/1e6:.0f} MB.")

    data = path.read_bytes()
    kind = _sniff(data[:2048])
    if kind == "pdf":
        return _load_pdf(path, data)
    if kind in ("jpeg", "png", "tiff", "webp"):
        return _load_image(path, data)
    raise DocumentError(
        "unsupported_type",
        f"Not a PDF or a supported image (jpg/png/tiff/webp). Extension was '{path.suffix}'.",
    )
