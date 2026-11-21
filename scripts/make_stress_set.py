"""Build degraded copies of the labelled documents to find where extraction breaks.

The 10 labelled documents are mostly clean, and the baseline gets them all right,
so they cannot show failure modes. This script re-renders every labelled document
as a *scanned* PDF (image only, no text layer) under several degradations and copies
the ground truth next to it, so `evaluate.py --labelled data/stress/<variant>` works.

    python scripts/make_stress_set.py            # writes data/stress/<variant>/

Variants (deterministic: fixed random seed):
    lowres      ~75 dpi, JPEG quality 35           (cheap fax / thumbnail)
    tiny        ~50 dpi, JPEG quality 30           (barely legible)
    blur_noise  100 dpi, Gaussian blur r=1.6, noise, JPEG q=45
    rot90       rotated 90 degrees clockwise       (like sample U05)
    rot180      upside down
    phone       5 degree skew, uneven lighting, slight blur, JPEG q=50
"""

from __future__ import annotations

import io
import json
import random
import shutil
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageEnhance, ImageFilter

SRC = Path("data/sample_pack/labelled")
DST = Path("data/stress")


def page_images(path: Path, dpi: int) -> list[Image.Image]:
    if path.suffix.lower() == ".pdf":
        with pymupdf.open(path) as pdf:
            return [Image.open(io.BytesIO(p.get_pixmap(dpi=dpi).tobytes("png"))).convert("RGB") for p in pdf]
    img = Image.open(path).convert("RGB")
    scale = dpi / 150  # treat sample photos as ~150 dpi
    return [img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)]


def jpeg(img: Image.Image, q: int) -> Image.Image:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=q)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def add_noise(img: Image.Image, amount: int, rng: random.Random) -> Image.Image:
    noise = Image.effect_noise(img.size, amount).convert("RGB")
    return Image.blend(img, noise, 0.12)


def lighting(img: Image.Image) -> Image.Image:
    """Darken one side, as with a phone held over a desk."""
    w, h = img.size
    grad = Image.linear_gradient("L").rotate(90).resize((w, h))
    return Image.blend(img, Image.composite(img, ImageEnhance.Brightness(img).enhance(0.55), grad), 0.8)


VARIANTS = {
    "lowres":     dict(dpi=75,  fn=lambda im, r: jpeg(im, 35)),
    "tiny":       dict(dpi=50,  fn=lambda im, r: jpeg(im, 30)),
    "blur_noise": dict(dpi=100, fn=lambda im, r: jpeg(add_noise(im.filter(ImageFilter.GaussianBlur(1.6)), 60, r), 45)),
    "rot90":      dict(dpi=120, fn=lambda im, r: jpeg(im.rotate(-90, expand=True), 70)),
    "rot180":     dict(dpi=120, fn=lambda im, r: jpeg(im.rotate(180, expand=True), 70)),
    "phone":      dict(dpi=110, fn=lambda im, r: jpeg(lighting(im.rotate(5, expand=True, fillcolor=(90, 80, 70))
                                                                .filter(ImageFilter.GaussianBlur(0.9))), 50)),
}


def to_pdf(images: list[Image.Image], out: Path) -> None:
    doc = pymupdf.open()
    for im in images:
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=95)
        # size the page so the loader's 150-dpi render gives back the same pixel count
        page = doc.new_page(width=im.width * 72 / 150, height=im.height * 72 / 150)
        page.insert_image(page.rect, stream=buf.getvalue())
    doc.save(out)
    doc.close()


def main() -> int:
    if not SRC.is_dir():
        print(f"missing {SRC}", file=sys.stderr)
        return 1
    rng = random.Random(42)
    for name, spec in VARIANTS.items():
        out = DST / name
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        for src in sorted(p for p in SRC.iterdir() if p.suffix.lower() in (".pdf", ".jpg", ".jpeg", ".png")):
            imgs = [spec["fn"](im, rng) for im in page_images(src, spec["dpi"])]
            to_pdf(imgs, out / f"{src.stem}.pdf")
            shutil.copy(SRC / f"{src.stem}.json", out / f"{src.stem}.json")
        print(f"wrote {out}  ({spec['dpi']} dpi)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
