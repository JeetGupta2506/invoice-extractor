"""load -> LLM -> parse -> validate -> (retry once with feedback) -> result + meta.

Statuses
  ok              all error-level checks passed on the first attempt
  ok_after_retry  first attempt failed a check, the retry fixed it
  flagged         still failing after the retry; result returned but needs_review=true
  rejected        bad input caught before the LLM (corrupt, empty, blank, ...)
  failed          LLM call failed (timeout, rate limit, auth) or never produced
                  schema-valid JSON; no result
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from .llm import LLMClient, LLMError, LLMResponse, inline_refs
from .loader import DocumentError, LoadedDocument, load_document
from .pricing import cost_usd
from .prompts import PROMPT_VERSION, SYSTEM_PROMPT, USER_PROMPT, retry_feedback
from .schema import LLMExtraction, to_result
from .validate import Check, check_resolution, failed, run_checks

MAX_LLM_ROUNDS = 2  # first answer + one corrective retry
RESPONSE_SCHEMA = inline_refs(LLMExtraction.model_json_schema())


@dataclass
class Outcome:
    file: str
    status: str
    result: Optional[dict]
    needs_review: bool
    review_reasons: list[str] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    error: Optional[dict] = None
    document: dict = field(default_factory=dict)
    llm: dict = field(default_factory=dict)
    raw_extraction: Optional[dict] = None

    def meta(self) -> dict:
        return {
            "file": self.file,
            "status": self.status,
            "needs_review": self.needs_review,
            "review_reasons": self.review_reasons,
            "error": self.error,
            "checks": [c.to_dict() for c in self.checks],
            "document": self.document,
            "llm": self.llm,
            "raw_extraction": self.raw_extraction,
        }


def _parse(resp: LLMResponse) -> tuple[Optional[LLMExtraction], Optional[dict], list[str]]:
    """Returns (extraction, result_dict, problems)."""
    try:
        data = json.loads(resp.text)
    except json.JSONDecodeError as e:
        return None, None, [f"response is not valid JSON: {e}"]
    try:
        ext = LLMExtraction.model_validate(data)
    except ValidationError as e:
        return None, None, [f"{'.'.join(map(str, er['loc']))}: {er['msg']}" for er in e.errors()[:8]]
    return ext, to_result(ext), []


def extract_document(path: str | Path, client: LLMClient, input_mode: str = "image+text") -> Outcome:
    path = Path(path)
    out = Outcome(file=path.name, status="failed", result=None, needs_review=True)

    # 1. load (bad-input gate, costs nothing)
    try:
        doc: LoadedDocument = load_document(path)
    except DocumentError as e:
        out.status = "rejected"
        out.error = e.to_dict()
        out.review_reasons = [f"rejected: {e.code}"]
        return out
    out.document = {"source_kind": doc.source_kind, "pages": doc.page_count,
                    "has_text_layer": doc.text_layer is not None}
    mode = input_mode if (doc.text_layer or input_mode == "image") else "image"

    # 2. LLM rounds
    conversation = [USER_PROMPT]
    usage = {"input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0, "latency_s": 0.0}
    rounds = []
    ext = result = None
    checks: list[Check] = []
    t0 = time.monotonic()

    for round_no in range(1, MAX_LLM_ROUNDS + 1):
        try:
            resp = client.generate(doc, SYSTEM_PROMPT, conversation, RESPONSE_SCHEMA, mode)
        except LLMError as e:
            out.status = "failed"
            out.error = e.to_dict()
            out.review_reasons = [f"llm_error: {e.code}"]
            break

        usage["input_tokens"] += resp.input_tokens
        usage["output_tokens"] += resp.output_tokens
        usage["thinking_tokens"] += resp.thinking_tokens
        usage["latency_s"] += resp.latency_s

        new_ext, new_result, problems = _parse(resp)
        if new_result is not None:
            # keep the latest schema-valid answer; a garbled retry never replaces a usable one
            ext, result = new_ext, new_result
            checks = run_checks(ext, result)
            if result.get("is_invoice"):
                res = check_resolution(doc.source_kind, [(p.width, p.height) for p in doc.pages])
                if res:
                    checks.append(res)
            problems = [f"{c.name}: {c.detail}" for c in failed(checks, "error")]
        rounds.append({"round": round_no, "cached": resp.cached, "problems": problems,
                       "input_tokens": resp.input_tokens,
                       "output_tokens": resp.output_tokens, "thinking_tokens": resp.thinking_tokens})

        if new_result is not None and not problems:
            out.status = "ok" if round_no == 1 else "ok_after_retry"
            break
        if round_no < MAX_LLM_ROUNDS:
            conversation += [resp.text, retry_feedback(problems)]
        else:
            out.status = "flagged" if result is not None else "failed"
            if result is None:
                out.error = {"code": "invalid_llm_output", "message": "; ".join(problems)}

    # 3. assemble
    out.checks = checks
    out.raw_extraction = ext.model_dump() if ext else None
    if out.status in ("ok", "ok_after_retry", "flagged"):
        out.result = result
        reasons = [f"{c.name}: {c.detail}" for c in failed(checks)]
        out.review_reasons = reasons
        out.needs_review = bool(reasons)
    billed_out = usage["output_tokens"] + usage["thinking_tokens"]
    cost = cost_usd(client.model, usage["input_tokens"], billed_out)
    out.llm = {
        "model": client.model,
        "thinking_level": getattr(client, "thinking_level", None),
        "prompt_version": PROMPT_VERSION,
        "input_mode": mode,
        "rounds": rounds,
        **usage,
        "latency_s": round(usage["latency_s"], 2),
        "billed_output_tokens": billed_out,
        "cost_usd": round(cost, 6) if cost is not None else None,
        "wall_time_s": round(time.monotonic() - t0, 2),
    }
    return out
