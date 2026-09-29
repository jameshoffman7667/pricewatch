import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.extract import extract, extract_price_from_text  # noqa: E402


def test_price_from_plain_text_usd():
    assert extract_price_from_text("$1,299.99") == 1299.99


def test_price_from_plain_text_eu_format():
    assert extract_price_from_text("1.234,56 EUR") == 1234.56


def test_price_from_plain_text_simple():
    assert extract_price_from_text("Only 19.99 today") == 19.99


def test_auto_detect_itemprop_price():
    html = """
    <html><body>
      <div class="stuff">not this</div>
      <span itemprop="price" content="149.00">$149.00</span>
    </body></html>
    """
    r = extract(html, selector=None, selector_type="auto")
    assert r.price == 149.00
    assert r.matched_selector == '[itemprop="price"]'


def test_auto_detect_meta_og_price():
    html = """
    <html><head>
      <meta property="og:price:amount" content="59.95">
    </head><body></body></html>
    """
    r = extract(html, selector=None, selector_type="auto")
    assert r.price == 59.95


def test_css_selector_mode():
    html = '<div class="price-current">$42.50</div>'
    r = extract(html, selector=".price-current", selector_type="css")
    assert r.price == 42.50


def test_css_selector_no_match_returns_none_price():
    html = "<div>nothing here</div>"
    r = extract(html, selector=".price-current", selector_type="css")
    assert r.price is None
    assert r.raw_text is None


def test_regex_mode():
    html = '<script>var data = {"price": "89.99"};</script>'
    r = extract(html, selector=r'"price":\s*"([\d.]+)"', selector_type="regex")
    assert r.price == 89.99


def test_content_hash_changes_with_content():
    html_a = '<div class="price">$10.00</div>'
    html_b = '<div class="price">$20.00</div>'
    ra = extract(html_a, ".price", "css")
    rb = extract(html_b, ".price", "css")
    assert ra.content_hash != rb.content_hash


def test_content_hash_stable_for_same_content():
    html = '<div class="price">$10.00</div>'
    ra = extract(html, ".price", "css")
    rb = extract(html, ".price", "css")
    assert ra.content_hash == rb.content_hash


def test_extra_regex_narrows_matched_text():
    html = '<div class="price">Was $99.00, Now $79.00</div>'
    r = extract(html, ".price", "css", extra_regex=r"Now \$(\d+\.\d+)")
    assert r.price == 79.00


def test_amazon_style_offscreen_price():
    html = """
    <span class="a-price">
      <span class="a-offscreen">$249.99</span>
      <span aria-hidden="true">$249.99</span>
    </span>
    """
    r = extract(html, selector=None, selector_type="auto")
    assert r.price == 249.99


if __name__ == "__main__":
    import pytest  # optional
    raise SystemExit(pytest.main([__file__, "-v"]))
