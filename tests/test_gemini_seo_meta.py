"""
Regression coverage for GeminiModule.generate_seo_meta()'s JSON extraction.

Bug history: the original implementation used `raw.strip().strip("```json")`
to remove a markdown code fence — str.strip(chars) removes any of the given
*characters* from each end, not the literal substring, and the fallback on
a parse failure returned slices of the raw, un-parsed model text. Whenever
Gemini added any preamble/trailing commentary, or a product title contained
an unescaped quote that broke the JSON mid-string, this wrote literal
garbage like `{"meta_title": "The Goat Hoodie...` straight to Shopify's
meta title field as if it were real copy.
"""

from modules.gemini import GeminiModule


def _meta(raw_response: str) -> dict:
    module = GeminiModule.__new__(GeminiModule)  # skip __init__ (no credentials needed)
    module.generate = lambda *a, **k: raw_response
    return module.generate_seo_meta("The Goat Hoodie", "product")


def test_parses_clean_fenced_json():
    raw = '```json\n{"meta_title": "The Goat Hoodie | LB", "meta_description": "Shop now."}\n```'
    result = _meta(raw)
    assert result == {"meta_title": "The Goat Hoodie | LB", "meta_description": "Shop now."}


def test_parses_single_line_fenced_json():
    raw = '```json{"meta_title": "The Goat Hoodie | LB", "meta_description": "Shop now."}```'
    result = _meta(raw)
    assert result == {"meta_title": "The Goat Hoodie | LB", "meta_description": "Shop now."}


def test_parses_json_with_preamble_text():
    """A model response with leading commentary must still parse, not
    fall through to writing that commentary as the title."""
    raw = (
        "Here is the SEO meta content:\n"
        '```json\n{"meta_title": "The Goat Hoodie | LB", "meta_description": "Shop now."}\n```'
    )
    result = _meta(raw)
    assert result == {"meta_title": "The Goat Hoodie | LB", "meta_description": "Shop now."}


def test_never_returns_raw_text_when_json_is_unparseable():
    """Regression for the exact reported symptom: an unescaped quote inside
    the generated title breaks json.loads mid-string. The old fallback
    wrote raw[:60] (literally '```json\\n{"meta_title": ...') as the title.
    The fixed version must signal failure (empty strings), never raw text."""
    raw = '```json\n{"meta_title": "The "Goat" Hoodie | LB", "meta_description": "Shop now."}\n```'
    result = _meta(raw)
    assert result == {"meta_title": "", "meta_description": ""}
    assert "```" not in result["meta_title"]
    assert "{" not in result["meta_title"]


def test_returns_empty_strings_on_completely_unparseable_response():
    raw = "I cannot generate that right now."
    result = _meta(raw)
    assert result == {"meta_title": "", "meta_description": ""}


def test_returns_empty_strings_when_required_keys_are_missing():
    raw = '```json\n{"title": "wrong key name"}\n```'
    result = _meta(raw)
    assert result == {"meta_title": "", "meta_description": ""}


def test_rejects_non_string_schema_invalid_values():
    """Regression (Codex review on PR #126): valid JSON with the wrong value
    type (array/number/bool) must not be coerced into Python display text
    like "['The Goat Hoodie']" or "True" and handed back as if it were a
    real title/description."""
    raw = '```json\n{"meta_title": ["The Goat Hoodie"], "meta_description": true}\n```'
    result = _meta(raw)
    assert result == {"meta_title": "", "meta_description": ""}
