"""Thin wrapper around the Gemini API.

Responsibilities:
  * build the request (page images + optional text layer + JSON schema)
  * timeouts and retries with exponential backoff for transient failures
    (timeouts, HTTP 429 rate limits, 5xx) - non-transient errors fail fast
  * report token usage so we can compute cost
  * an on-disk response cache, so re-running the eval costs nothing and is
    reproducible. The key covers file bytes, model, prompt version, thinking
    level, input mode and the conversation so far, so any change is a cache miss.

Everything provider-specific is in this file. Swapping to another provider means
writing another class with the same ``generate`` signature.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Protocol

from .loader import LoadedDocument

DEFAULT_MODEL = "gemini-3.5-flash-lite"

# Per the Gemini docs (checked 2026-11-21): Flash-Lite defaults to "minimal"
# thinking; 3.8 Flash rejects "minimal", so it gets "low".
DEFAULT_THINKING = {
    "gemini-3.5-flash-lite": "minimal",
    "gemini-3.1-flash-lite": "minimal",
    "gemini-3.8-flash": "low",
    "gemini-3.6-flash": "minimal",
}

RETRYABLE_HTTP = {408, 429, 500, 502, 503, 504}
MAX_WAIT_S = 60  # if the server asks us to wait longer than this, don't retry


def _retry_delay_s(message: str) -> Optional[float]:
    """Read the server's RetryInfo, e.g. "'retryDelay': '5149s'", from an error message."""
    import re

    m = re.search(r"retryDelay'?\"?:\s*'?\"?(\d+(?:\.\d+)?)s", message)
    return float(m.group(1)) if m else None


class LLMError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int      # visible answer tokens
    thinking_tokens: int    # billed at the output rate
    latency_s: float
    cached: bool = False

    @property
    def billed_output_tokens(self) -> int:
        return self.output_tokens + self.thinking_tokens


class LLMClient(Protocol):
    model: str

    def generate(
        self,
        doc: LoadedDocument,
        system_prompt: str,
        conversation: list[str],
        response_schema: dict,
        input_mode: str,
    ) -> LLMResponse: ...


# ---------------------------------------------------------------------------
def inline_refs(schema: dict) -> dict:
    """Pydantic emits $defs/$ref; inline them so any JSON-schema consumer is happy."""
    defs = schema.get("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                return walk(defs[name])
            return {k: walk(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


class ResponseCache:
    def __init__(self, directory: str | Path = ".cache/llm", enabled: bool = True):
        self.dir = Path(directory)
        self.enabled = enabled

    @staticmethod
    def key(*parts: str | bytes) -> str:
        h = hashlib.sha256()
        for p in parts:
            h.update(p if isinstance(p, bytes) else p.encode("utf-8"))
            h.update(b"\x00")
        return h.hexdigest()

    def get(self, key: str) -> Optional[LLMResponse]:
        if not self.enabled:
            return None
        f = self.dir / f"{key}.json"
        if not f.exists():
            return None
        data = json.loads(f.read_text(encoding="utf-8"))
        data["cached"] = True
        return LLMResponse(**data)

    def put(self, key: str, resp: LLMResponse) -> None:
        if not self.enabled:
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        d = asdict(resp)
        d["cached"] = False
        (self.dir / f"{key}.json").write_text(json.dumps(d, indent=1), encoding="utf-8")


# ---------------------------------------------------------------------------
class GeminiClient:
    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        thinking_level: Optional[str] = None,
        timeout_s: Optional[float] = None,
        max_attempts: int = 4,
        cache: Optional[ResponseCache] = None,
    ):
        self.model = model or os.getenv("GEMINI_MODEL") or DEFAULT_MODEL
        self.thinking_level = thinking_level or DEFAULT_THINKING.get(self.model, "low")
        self.timeout_s = float(timeout_s or os.getenv("LLM_TIMEOUT_S") or 90)
        self.max_attempts = max_attempts
        self.cache = cache or ResponseCache()
        self._api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self._client = None  # created lazily so cached runs need no key

    # -- plumbing ----------------------------------------------------------
    def _sdk(self):
        if self._client is None:
            if not self._api_key:
                raise LLMError(
                    "missing_api_key",
                    "GEMINI_API_KEY is not set. Copy .env.example to .env and add your key.",
                )
            from google import genai
            from google.genai import types

            self._client = genai.Client(
                api_key=self._api_key,
                http_options=types.HttpOptions(timeout=int(self.timeout_s * 1000)),
            )
        return self._client

    def _contents(self, doc: LoadedDocument, conversation: list[str], input_mode: str):
        """conversation = [user_msg, model_reply, user_msg, ...]; images go with the first turn."""
        from google.genai import types

        first: list = []
        if input_mode in ("image", "image+text"):
            first += [types.Part.from_bytes(data=p.data, mime_type=p.mime_type) for p in doc.pages]
        if input_mode in ("text", "image+text") and doc.text_layer:
            from .prompts import TEXT_LAYER_HEADER

            first.append(types.Part.from_text(text=f"{TEXT_LAYER_HEADER}\n{doc.text_layer}"))
        if input_mode == "text" and not doc.text_layer:
            raise LLMError("no_text_layer", "input_mode=text but the document has no text layer (scan/photo).")

        contents = []
        for i, msg in enumerate(conversation):
            if i % 2 == 0:
                parts = (first if i == 0 else []) + [types.Part.from_text(text=msg)]
                contents.append(types.Content(role="user", parts=parts))
            else:
                contents.append(types.Content(role="model", parts=[types.Part.from_text(text=msg)]))
        return contents

    def _call_once(self, doc, system_prompt, conversation, response_schema, input_mode) -> LLMResponse:
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0,
            response_mime_type="application/json",
            response_json_schema=response_schema,
            thinking_config=types.ThinkingConfig(thinking_level=self.thinking_level),
            max_output_tokens=8192,
        )
        t0 = time.monotonic()
        try:
            resp = self._sdk().models.generate_content(
                model=self.model,
                contents=self._contents(doc, conversation, input_mode),
                config=config,
            )
        except errors.APIError as e:
            code = getattr(e, "code", None) or 0
            delay = _retry_delay_s(str(e))
            if code == 429 and delay is not None and delay > MAX_WAIT_S:
                # e.g. a daily quota: the server says "retry in 1h25m". Backing off
                # for a few seconds cannot help, so fail fast with a distinct code.
                raise LLMError("quota_exhausted",
                               f"HTTP 429 quota exhausted; server asks to retry in {delay/60:.0f} min. {e}") from e
            if code in RETRYABLE_HTTP:
                kind = "rate_limited" if code == 429 else "server_error"
                raise LLMError(kind, f"HTTP {code}: {e}", retryable=True) from e
            if code in (401, 403):
                raise LLMError("auth_error", f"HTTP {code}: check GEMINI_API_KEY. {e}") from e
            raise LLMError("api_error", f"HTTP {code}: {e}") from e
        except Exception as e:  # network-level: timeouts, connection resets
            name = type(e).__name__.lower()
            if "timeout" in name or "timedout" in name:
                raise LLMError("timeout", f"No response within {self.timeout_s:.0f}s ({type(e).__name__})", retryable=True) from e
            if "connect" in name or "network" in name or "remoteprotocol" in name:
                raise LLMError("network_error", f"{type(e).__name__}: {e}", retryable=True) from e
            raise
        latency = time.monotonic() - t0

        text = resp.text
        if not text:
            reason = None
            if resp.candidates:
                reason = resp.candidates[0].finish_reason
            raise LLMError("empty_response", f"Model returned no text (finish_reason={reason}).", retryable=True)

        u = resp.usage_metadata
        return LLMResponse(
            text=text,
            model=self.model,
            input_tokens=(u.prompt_token_count or 0) if u else 0,
            output_tokens=(u.candidates_token_count or 0) if u else 0,
            thinking_tokens=(u.thoughts_token_count or 0) if u else 0,
            latency_s=round(latency, 2),
        )

    # -- public ------------------------------------------------------------
    def generate(self, doc, system_prompt, conversation, response_schema, input_mode="image+text") -> LLMResponse:
        from .prompts import PROMPT_VERSION

        key = self.cache.key(
            doc.file_bytes, self.model, PROMPT_VERSION, self.thinking_level, input_mode,
            system_prompt, json.dumps(response_schema, sort_keys=True), *conversation,
        )
        hit = self.cache.get(key)
        if hit:
            return hit

        last: Optional[LLMError] = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                resp = self._call_once(doc, system_prompt, conversation, response_schema, input_mode)
                self.cache.put(key, resp)
                return resp
            except LLMError as e:
                last = e
                if not e.retryable or attempt == self.max_attempts:
                    break
                # exponential backoff with jitter: ~2s, 4s, 8s (longer for rate limits)
                base = 5 if e.code == "rate_limited" else 2
                time.sleep(base * 2 ** (attempt - 1) + random.uniform(0, 1))
        assert last is not None
        if last.retryable:
            last.message = f"{last.message} (gave up after {self.max_attempts} attempts)"
        raise last
