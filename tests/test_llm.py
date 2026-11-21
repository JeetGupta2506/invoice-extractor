from invoice_extractor.llm import _retry_delay_s, inline_refs
from invoice_extractor.pipeline import RESPONSE_SCHEMA


def test_retry_delay_parsing():
    # shape of a real Gemini 429 for an exhausted daily free-tier quota
    msg = "429 RESOURCE_EXHAUSTED. {... 'retryDelay': '5149s'}]}}"
    assert _retry_delay_s(msg) == 5149.0
    assert _retry_delay_s('"retryDelay": "12.5s"') == 12.5
    assert _retry_delay_s("500 INTERNAL") is None


def test_response_schema_has_no_refs():
    import json
    assert "$ref" not in json.dumps(RESPONSE_SCHEMA)
    s = inline_refs({"$defs": {"A": {"type": "string"}}, "properties": {"x": {"$ref": "#/$defs/A"}}})
    assert s == {"properties": {"x": {"type": "string"}}}
