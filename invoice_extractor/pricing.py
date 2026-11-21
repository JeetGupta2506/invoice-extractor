"""Cost calculation.

cost = input_tokens  * input_price  / 1e6
     + (output_tokens + thinking_tokens) * output_price / 1e6

Token counts come from the API's own usage_metadata on every call (not from
an estimate). Thinking tokens are billed at the output rate.

Prices: Gemini Developer API, Standard paid tier, USD per 1M tokens.
Source: https://ai.google.dev/gemini-api/docs/pricing  (checked 2026-11-21)
Images are billed at the text/image/video input rate.
The free tier costs $0; we report what the run would cost on the paid tier.
"""

from __future__ import annotations

PRICING_SOURCE = "https://ai.google.dev/gemini-api/docs/pricing (Standard tier, checked 2026-11-21)"

PRICES_USD_PER_MTOK: dict[str, dict[str, float]] = {
    "gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50},
    "gemini-3.1-flash-lite": {"input": 0.25, "output": 1.50},
    # introductory price until 2026-12-31; $1.50 / $7.50 from 2027-01-01
    "gemini-3.8-flash": {"input": 0.75, "output": 3.75},
    "gemini-3.6-flash": {"input": 0.75, "output": 3.75},
}


def cost_usd(model: str, input_tokens: int, billed_output_tokens: int) -> float | None:
    p = PRICES_USD_PER_MTOK.get(model)
    if p is None:
        return None
    return input_tokens * p["input"] / 1e6 + billed_output_tokens * p["output"] / 1e6
