"""Evaluate the extractor on the labelled documents and print a results table.

    python evaluate.py                       # run extractor on data/sample_pack/labelled, score, print
    python evaluate.py --offline             # score the JSON already in outputs/ (no API key needed)
    python evaluate.py --model gemini-3.8-flash --input-mode image

Responses are cached in .cache/, so re-running is free and gives the same numbers;
pass --no-cache to force fresh API calls. Matching rules are in
invoice_extractor/matching.py (and REPORT.md). Results are also written to
eval_results/<tag>.json and eval_results/<tag>.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from invoice_extractor.matching import FIELDS, compare
from invoice_extractor.pricing import PRICING_SOURCE

DEFAULT_LABELLED = Path("data/sample_pack/labelled")
SUPPORTED_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
SHORT = {"is_invoice": "is_inv", "vendor": "vendor", "invoice_number": "inv_no",
         "invoice_date": "date", "currency": "curr", "line_items": "lines",
         "tax_total": "tax", "total": "total"}
TICK, CROSS = "✓", "✗"


def collect_live(labelled: Path, args) -> list[dict]:
    from invoice_extractor.llm import GeminiClient, ResponseCache
    from invoice_extractor.pipeline import extract_document

    client = GeminiClient(model=args.model, thinking_level=args.thinking,
                          cache=ResponseCache(enabled=not args.no_cache))
    records = []
    docs = sorted(f for f in labelled.iterdir() if f.suffix.lower() in SUPPORTED_EXT)
    for i, f in enumerate(docs, 1):
        print(f"  [{i}/{len(docs)}] {f.name} ...", file=sys.stderr, end="", flush=True)
        o = extract_document(f, client, input_mode=args.input_mode)
        print(f" {o.status}", file=sys.stderr)
        records.append({"file": f.name, "stem": f.stem, "result": o.result, "meta": o.meta()})
    return records


def collect_offline(labelled: Path, pred_dir: Path) -> list[dict]:
    records = []
    for f in sorted(x for x in labelled.iterdir() if x.suffix.lower() in SUPPORTED_EXT):
        pj = pred_dir / f"{f.stem}.json"
        mj = pred_dir / "meta" / f"{f.stem}.meta.json"
        result = json.loads(pj.read_text(encoding="utf-8")) if pj.exists() else None
        if result is not None and "error" in result:
            result = None
        meta = json.loads(mj.read_text(encoding="utf-8")) if mj.exists() else {}
        records.append({"file": f.name, "stem": f.stem, "result": result, "meta": meta})
    return records


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:5.1f}%" if d else "   n/a"


def render(records: list[dict], labelled: Path) -> tuple[str, dict]:
    lines: list[str] = []
    w = lines.append
    per_doc = []
    for r in records:
        gold = json.loads((labelled / f"{r['stem']}.json").read_text(encoding="utf-8"))
        cmp = compare(r["result"], gold)
        per_doc.append({**r, "gold": gold, "cmp": cmp})

    # ---- per-document table
    w("PER-DOCUMENT RESULTS  (✓ = matches ground truth)")
    head = f"{'doc':<9}{'source':<13}{'status':<16}{'review':<8}" + "".join(f"{SHORT[f]:>8}" for f in FIELDS) + f"{'rows ok':>10}"
    w(head)
    w("-" * len(head))
    for d in per_doc:
        m = d["meta"] or {}
        src = (m.get("document") or {}).get("source_kind", "?")
        li = d["cmp"]["line_items"]
        cells = "".join(f"{(TICK if d['cmp'][f]['correct'] else CROSS):>8}" for f in FIELDS)
        w(f"{d['file']:<9}{src:<13}{m.get('status', '?'):<16}{('yes' if m.get('needs_review') else 'no'):<8}"
          f"{cells}{str(li.get('rows_matched', 0)) + '/' + str(li.get('n_gold', 0)):>10}")

    # ---- field accuracy
    n = len(per_doc)
    inv = [d for d in per_doc if d["gold"]["is_invoice"]]
    w("")
    w("FIELD-LEVEL ACCURACY")
    w(f"{'field':<16}{'all docs':>12}{'':>8}{'invoices only':>16}{'':>8}")
    w(f"{'':<16}{'(n=' + str(n) + ')':>12}{'':>8}{'(n=' + str(len(inv)) + ')':>16}")
    summary_fields = {}
    for f in FIELDS:
        c_all = sum(d["cmp"][f]["correct"] for d in per_doc)
        c_inv = sum(d["cmp"][f]["correct"] for d in inv)
        summary_fields[f] = {"correct": c_all, "n": n, "accuracy": c_all / n if n else None,
                             "correct_invoices_only": c_inv, "n_invoices": len(inv)}
        w(f"{f:<16}{c_all:>6}/{n:<3}{pct(c_all, n):>8}{c_inv:>10}/{len(inv):<3}{pct(c_inv, len(inv)):>8}")
    all_correct = sum(all(d["cmp"][f]["correct"] for f in FIELDS) for d in per_doc)
    cells_ok = sum(d["cmp"][f]["correct"] for d in per_doc for f in FIELDS)
    w(f"{'ALL FIELDS':<16}{cells_ok:>6}/{n*len(FIELDS):<3}{pct(cells_ok, n*len(FIELDS)):>8}"
      f"   (field-level micro average)")
    w(f"{'PERFECT DOCS':<16}{all_correct:>6}/{n:<3}{pct(all_correct, n):>8}   (every field correct)")

    # ---- line items row-level
    g_rows = sum(d["cmp"]["line_items"].get("n_gold", 0) for d in inv)
    p_rows = sum(d["cmp"]["line_items"].get("n_pred", 0) for d in inv)
    m_rows = sum(d["cmp"]["line_items"].get("rows_matched", 0) for d in inv)
    w("")
    w(f"LINE ITEMS, ROW LEVEL: {m_rows} rows fully correct | "
      f"recall {pct(m_rows, g_rows).strip()} of {g_rows} gold rows | "
      f"precision {pct(m_rows, p_rows).strip()} of {p_rows} predicted rows")

    # ---- errors in detail
    w("")
    w("ERRORS (prediction vs ground truth)")
    errors = []
    for d in per_doc:
        for f in FIELDS:
            c = d["cmp"][f]
            if c["correct"]:
                continue
            if f == "line_items":
                detail = "; ".join(c.get("issues") or [c.get("why", "")])
            else:
                detail = f"got {c.get('pred')!r}, expected {c.get('gold')!r}"
            errors.append({"doc": d["file"], "field": f, "detail": detail})
            w(f"  {d['file']:<9}{f:<15}{detail}")
    if not errors:
        w("  none")

    # ---- review flag vs errors (bonus)
    flagged = [d for d in per_doc if (d["meta"] or {}).get("needs_review")]
    with_err = [d for d in per_doc if not all(d["cmp"][f]["correct"] for f in FIELDS)]
    tp = [d for d in flagged if d in with_err]
    err_cells = len(errors)
    err_cells_flagged = sum(1 for e in errors if any(d["file"] == e["doc"] for d in flagged))
    w("")
    w("REVIEW FLAG vs ACTUAL ERRORS")
    w(f"  flagged docs: {len(flagged)}/{n}  |  docs with >=1 wrong field: {len(with_err)}/{n}")
    w(f"  flagged AND wrong: {len(tp)}  |  wrong but NOT flagged: {len(with_err) - len(tp)}  |  "
      f"flagged but correct: {len(flagged) - len(tp)}")
    w(f"  share of wrong fields that sit in flagged docs: {err_cells_flagged}/{err_cells}"
      f" ({pct(err_cells_flagged, err_cells).strip()})")
    for d in flagged:
        w(f"    {d['file']}: {'; '.join((d['meta'] or {}).get('review_reasons', []))[:160]}")

    # ---- cost
    llms_all = [(d["meta"] or {}).get("llm") or {} for d in per_doc]
    # average over documents where the model actually answered; failed calls are reported, not averaged in
    llms = [x for x in llms_all if x.get("rounds")]
    n_failed_calls = sum(1 for d in per_doc if (d["meta"] or {}).get("status") == "failed")
    w("")
    w("COST")
    if n_failed_calls:
        w(f"  WARNING: {n_failed_calls} document(s) failed at the LLM call and are excluded from the averages "
          f"(and scored as wrong above): "
          + ", ".join(f"{d['file']}={((d['meta'] or {}).get('error') or {}).get('code')}"
                      for d in per_doc if (d['meta'] or {}).get('status') == 'failed'))
    if llms:
        tin = sum(x.get("input_tokens", 0) for x in llms)
        tout = sum(x.get("output_tokens", 0) for x in llms)
        tthink = sum(x.get("thinking_tokens", 0) for x in llms)
        tcost = sum(x.get("cost_usd") or 0 for x in llms)
        retried = sum(1 for x in llms if len(x.get("rounds", [])) > 1)
        k = len(llms)
        w(f"  model {llms[0].get('model')} | thinking={llms[0].get('thinking_level')} | input mode={llms[0].get('input_mode')} | prompt {llms[0].get('prompt_version')}")
        w(f"  docs that called the LLM: {k} | docs needing a 2nd round: {retried}")
        w(f"  avg tokens/doc: in {tin / k:,.0f} | out {tout / k:,.0f} | thinking {tthink / k:,.0f}")
        w(f"  avg cost/doc: ${tcost / k:.6f} | total for {k} docs: ${tcost:.5f}")
        w(f"  avg latency/doc: {sum(x.get('latency_s', 0) for x in llms) / k:.1f}s")
        w(f"  prices: {PRICING_SOURCE}")
    else:
        w("  no LLM metadata available")

    summary = {
        "n_docs": n,
        "fields": summary_fields,
        "perfect_docs": all_correct,
        "line_rows": {"gold": g_rows, "pred": p_rows, "matched": m_rows},
        "errors": errors,
        "review": {"flagged": [d["file"] for d in flagged], "wrong": [d["file"] for d in with_err]},
        "llm": llms,
    }
    return "\n".join(lines), summary


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    load_dotenv()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labelled", default=str(DEFAULT_LABELLED), help="folder with Lxx.pdf/jpg + Lxx.json")
    ap.add_argument("--offline", action="store_true", help="score saved predictions instead of calling the API")
    ap.add_argument("--pred-dir", default="outputs", help="predictions folder for --offline")
    ap.add_argument("--model", default=None)
    ap.add_argument("--thinking", default=None, choices=["minimal", "low", "medium", "high"])
    ap.add_argument("--input-mode", default="image+text", choices=["image+text", "image", "text"])
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--tag", default=None, help="name for the eval_results/ files")
    args = ap.parse_args(argv)

    labelled = Path(args.labelled)
    if not labelled.is_dir():
        print(f"Labelled folder not found: {labelled}. See README (put the sample pack in data/sample_pack).",
              file=sys.stderr)
        return 1

    if not args.offline and not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")) \
            and not Path(".cache/llm").is_dir():
        print("GEMINI_API_KEY is not set (copy .env.example to .env and add a key).\n"
              "To score the committed outputs/ without a key, run: python evaluate.py --offline", file=sys.stderr)
        return 1

    if args.offline:
        records = collect_offline(labelled, Path(args.pred_dir))
    else:
        print("Running extractor on labelled documents:", file=sys.stderr)
        records = collect_live(labelled, args)

    text, summary = render(records, labelled)
    print(text)

    llm0 = (summary["llm"] or [{}])[0]
    tag = args.tag or ("offline" if args.offline else
                       f"{llm0.get('model', 'model')}__{llm0.get('thinking_level')}__{args.input_mode.replace('+', '_')}")
    out = Path("eval_results")
    out.mkdir(exist_ok=True)
    (out / f"{tag}.md").write_text("```\n" + text + "\n```\n", encoding="utf-8")
    (out / f"{tag}.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nSaved eval_results/{tag}.md and .json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
