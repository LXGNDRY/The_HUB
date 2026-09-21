from scripts.seo_meta_rewrite import (
    DESC_MAX,
    TITLE_MAX,
    _fallback_meta,
    _truncate,
    generate_meta,
    resolve_meta,
)


def test_truncate_leaves_short_text_untouched():
    assert _truncate("Short Title", 60) == "Short Title"


def test_truncate_collapses_whitespace_and_clips_long_text():
    text = "  The   Legendary   " + "X" * 100
    result = _truncate(text, 60)
    assert len(result) <= 60
    assert result.endswith("…")
    assert "  " not in result


def test_fallback_meta_uses_only_live_title_no_fabricated_specs():
    """Regression: the prior hardcoded script invented specific GSM/material
    claims baked in at generation time, which went stale the moment a
    product was renamed. The fallback generator must only ever reflect the
    live title passed in."""
    seo_title, seo_desc = _fallback_meta("Classic Crewneck Cotton T-Shirt", "product")

    assert "Classic Crewneck Cotton T-Shirt" in seo_title
    assert seo_title.endswith("Legendary Branding")
    assert len(seo_title) <= TITLE_MAX
    assert "Classic Crewneck Cotton T-Shirt" in seo_desc
    assert len(seo_desc) <= DESC_MAX
    assert "GSM" not in seo_desc  # no fabricated fabric-weight claims


def test_fallback_meta_collection_wording_differs_from_product():
    _, product_desc = _fallback_meta("Hoodies", "product")
    _, collection_desc = _fallback_meta("Hoodies", "collection")
    assert "product" in product_desc
    assert "collection" in collection_desc


def test_generate_meta_falls_back_when_gemini_is_none():
    seo_title, seo_desc = generate_meta(None, "Wave Runner Boxy Tee", "product")
    assert "Wave Runner Boxy Tee" in seo_title
    assert len(seo_title) <= TITLE_MAX
    assert len(seo_desc) <= DESC_MAX


def test_generate_meta_falls_back_when_gemini_returns_incomplete_result():
    class _StubGemini:
        def generate_seo_meta(self, page_title, page_type):
            return {"meta_title": "", "meta_description": ""}

    seo_title, _ = generate_meta(_StubGemini(), "Mini Goat Oversized T-Shirt", "product")
    assert "Mini Goat Oversized T-Shirt" in seo_title


def test_generate_meta_uses_gemini_result_when_valid():
    class _StubGemini:
        def generate_seo_meta(self, page_title, page_type):
            return {"meta_title": f"{page_title} Deal | LB", "meta_description": f"Shop {page_title} now."}

    seo_title, seo_desc = generate_meta(_StubGemini(), "The Goat Hoodie", "product")
    assert seo_title == "The Goat Hoodie Deal | LB"
    assert seo_desc == "Shop The Goat Hoodie now."


def test_generate_meta_falls_back_when_gemini_raises():
    class _BrokenGemini:
        def generate_seo_meta(self, page_title, page_type):
            raise RuntimeError("network error")

    seo_title, _ = generate_meta(_BrokenGemini(), "Stay Rich Loose Fit T-Shirt", "product")
    assert "Stay Rich Loose Fit T-Shirt" in seo_title


def test_resolve_meta_skips_when_both_fields_already_set():
    title, desc, changed = resolve_meta(
        None, "The Goat Hoodie", "product", "Curated Title", "Curated description.", overwrite=False
    )
    assert not changed
    assert title == "Curated Title"
    assert desc == "Curated description."


def test_resolve_meta_preserves_curated_title_when_only_description_is_blank():
    """Regression: a curated meta title must survive a blank description
    getting filled in — the two fields are independent, not all-or-nothing."""
    title, desc, changed = resolve_meta(
        None, "The Goat Hoodie", "product", "Hand-Curated Title | LB", "", overwrite=False
    )
    assert changed
    assert title == "Hand-Curated Title | LB"
    assert desc != ""


def test_resolve_meta_preserves_curated_description_when_only_title_is_blank():
    title, desc, changed = resolve_meta(
        None, "The Goat Hoodie", "product", "", "Hand-curated description.", overwrite=False
    )
    assert changed
    assert desc == "Hand-curated description."
    assert title != ""


def test_resolve_meta_fills_both_when_both_blank():
    title, desc, changed = resolve_meta(None, "The Goat Hoodie", "product", "", "", overwrite=False)
    assert changed
    assert title != "" and desc != ""


def test_resolve_meta_overwrite_regenerates_both_even_when_set():
    title, desc, changed = resolve_meta(
        None, "The Goat Hoodie", "product", "Old Title", "Old description.", overwrite=True
    )
    assert changed
    assert title != "Old Title"
    assert desc != "Old description."
