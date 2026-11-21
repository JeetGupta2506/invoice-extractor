"""Extract structured JSON from an invoice PDF or image.

Single file (prints the schema JSON to stdout, diagnostics to stderr):
    python extract.py invoice.pdf > out.json
    python extract.py invoice.pdf --meta          # result + validation/cost metadata

Batch (writes outputs/<name>.json and outputs/meta/<name>.meta.json):
    python extract.py --batch data/sample_pack/labelled data/sample_pack/unlabelled --out outputs

Exit codes (single file):
    0  ok
    2  extracted, but needs_review=true (a check failed or raised a warning)
    3  rejected input or LLM failure - stdout carries {"error": {...}}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from invoice_extractor.llm import GeminiClient, ResponseCache
from invoice_extractor.pipeline import extract_document

SUPPORTED_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}


def make_client(args) -> GeminiClient:
    return GeminiClient(
        model=args.model,
        thinking_level=args.thinking,
        cache=ResponseCache(enabled=not args.no_cache),
    )


def run_batch(args) -> int:
    client = make_client(args)
    out_dir = Path(args.out)
    (out_dir / "meta").mkdir(parents=True, exist_ok=True)
    files = []
    for d in args.batch:
        p = Path(d)
        files += sorted(f for f in (p.iterdir() if p.is_dir() else [p])
                        if f.is_file() and f.suffix.lower() in SUPPORTED_EXT)

    summary = []
    print(f"{'file':<12}{'status':<16}{'review':<8}{'in_tok':>8}{'out_tok':>8}{'cost_usd':>11}  notes", file=sys.stderr)
    for f in files:
        o = extract_document(f, client, input_mode=args.input_mode)
        stem = f.stem
        if o.result is not None:
            (out_dir / f"{stem}.json").write_text(json.dumps(o.result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        else:
            (out_dir / f"{stem}.json").write_text(json.dumps({"error": o.error}, indent=2) + "\n", encoding="utf-8")
        (out_dir / "meta" / f"{stem}.meta.json").write_text(
            json.dumps(o.meta(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        llm = o.llm or {}
        note = (o.error or {}).get("code") or "; ".join(r.split(":")[0] for r in o.review_reasons)
        print(f"{f.name:<12}{o.status:<16}{str(o.needs_review):<8}{llm.get('input_tokens', 0):>8}"
              f"{llm.get('billed_output_tokens', 0):>8}{(llm.get('cost_usd') or 0):>11.6f}  {note}", file=sys.stderr)
        summary.append({"file": f.name, "status": o.status, "needs_review": o.needs_review,
                        "review_reasons": o.review_reasons, "error": o.error,
                        **{k: llm.get(k) for k in ("model", "input_tokens", "output_tokens",
                                                   "thinking_tokens", "cost_usd", "latency_s")}})
    (out_dir / "run_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    costs = [s["cost_usd"] or 0 for s in summary]
    print(f"\n{len(files)} documents, total cost ${sum(costs):.4f}, "
          f"avg ${sum(costs)/max(len(costs),1):.6f}/doc -> {out_dir}/", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252 (no ₹/€)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    load_dotenv()

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?", help="PDF or image to extract")
    ap.add_argument("--batch", nargs="+", metavar="PATH", help="directories/files to process into --out")
    ap.add_argument("--out", default="outputs", help="output directory for --batch (default: outputs)")
    ap.add_argument("--meta", action="store_true", help="print {result, meta} instead of just the result")
    ap.add_argument("--model", default=None, help="Gemini model id (default: $GEMINI_MODEL or gemini-3.5-flash-lite)")
    ap.add_argument("--thinking", default=None, choices=["minimal", "low", "medium", "high"],
                    help="thinking level (default depends on model)")
    ap.add_argument("--input-mode", default="image+text", choices=["image+text", "image", "text"],
                    help="what to send: page images, PDF text layer, or both (default)")
    ap.add_argument("--no-cache", action="store_true", help="always call the API (ignore .cache/)")
    args = ap.parse_args(argv)

    if args.batch:
        return run_batch(args)
    if not args.file:
        ap.error("give a file, or --batch DIR")

    o = extract_document(args.file, make_client(args), input_mode=args.input_mode)
    if o.result is None:
        print(json.dumps({"error": o.error}, indent=2, ensure_ascii=False))
        print(f"[{o.status}] {o.error['code']}: {o.error['message']}", file=sys.stderr)
        return 3
    payload = {"result": o.result, "meta": o.meta()} if args.meta else o.result
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    llm = o.llm
    print(f"[{o.status}] needs_review={o.needs_review} tokens in={llm['input_tokens']} "
          f"out={llm['billed_output_tokens']} cost=${llm['cost_usd']}", file=sys.stderr)
    for r in o.review_reasons:
        print(f"  review: {r}", file=sys.stderr)
    return 2 if o.needs_review else 0


if __name__ == "__main__":
    sys.exit(main())
