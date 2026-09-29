import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.rfd import (  # noqa: E402
    extract_thread_id,
    parse_feed,
    parse_search_results,
    parse_thread_detail,
    _normalize_search_terms,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _read(name):
    with open(os.path.join(FIXTURES, name), "rb") as f:
        return f.read()


# ---------------------------------------------------------------- feed


def test_parse_feed_extracts_all_entries():
    entries = parse_feed(_read("rfd_feed_sample.xml"))
    assert len(entries) == 3


def test_parse_feed_splits_retailer_prefix():
    entries = parse_feed(_read("rfd_feed_sample.xml"))
    e = next(e for e in entries if e.thread_id == 2827328)
    assert e.retailer == "Amazon.ca"
    assert e.title == "Reolink Duo 2 PoE (4K Duo Lens) - $135.99"


def test_parse_feed_extracts_thread_id_from_query_link():
    entries = parse_feed(_read("rfd_feed_sample.xml"))
    ids = {e.thread_id for e in entries}
    assert ids == {2827328, 2827327, 2827259}


def test_parse_feed_canonicalizes_url_without_post_fragment():
    entries = parse_feed(_read("rfd_feed_sample.xml"))
    e = next(e for e in entries if e.thread_id == 2827328)
    assert e.rfd_url == "https://forums.redflagdeals.com/viewtopic.php?t=2827328"
    assert "#p" not in e.rfd_url


def test_parse_feed_extracts_author_and_thumbnail():
    entries = parse_feed(_read("rfd_feed_sample.xml"))
    e = next(e for e in entries if e.thread_id == 2827328)
    assert e.author == "DCabral242"
    assert e.thumbnail_url == "https://c.dam-img.rfdcontent.com/cms/012/106/496/600x600_smart_fit.jpg"


def test_parse_feed_handles_entry_with_no_thumbnail():
    entries = parse_feed(_read("rfd_feed_sample.xml"))
    e = next(e for e in entries if e.thread_id == 2827259)
    assert e.thumbnail_url is None
    assert e.retailer == "Costco"


# ---------------------------------------------------------------- thread id extraction


def test_extract_thread_id_from_query_form():
    assert extract_thread_id("https://forums.redflagdeals.com/viewtopic.php?t=2827328&p=41281200#p41281200") == 2827328


def test_extract_thread_id_from_slug_form():
    assert extract_thread_id("https://forums.redflagdeals.com/costco-level-ground-coffee-48-99-after-15-off-2827259/") == 2827259


def test_extract_thread_id_ignores_short_trailing_numbers():
    # e.g. pagination or forum-id style links shouldn't be mistaken for thread ids
    assert extract_thread_id("https://forums.redflagdeals.com/hot-deals-f9/") is None
    assert extract_thread_id("https://forums.redflagdeals.com/page-2/") is None


def test_extract_thread_id_returns_none_for_unrelated_url():
    assert extract_thread_id("https://www.costco.ca/s?keyword=Level+Ground") is None


# ---------------------------------------------------------------- thread detail


def test_parse_thread_detail_extracts_price_fields():
    detail = parse_thread_detail(_read("rfd_thread_sample.html").decode())
    assert detail.price == 48.99
    assert detail.original_price == 63.99
    assert detail.savings_text == "Save 23%"
    assert detail.expiry_text == "Not provided"


def test_parse_thread_detail_extracts_merchant_link():
    detail = parse_thread_detail(_read("rfd_thread_sample.html").decode())
    assert detail.merchant_url == "https://www.costco.ca/s?keyword=Level+Ground&refinement=brands%253DLevel%2520Ground"


def test_parse_thread_detail_extracts_ai_summary():
    detail = parse_thread_detail(_read("rfd_thread_sample.html").decode())
    assert len(detail.ai_summary_points) == 6
    assert "coffee beans" in detail.ai_summary_points[0]
    assert detail.ai_summary_label == "AI-generated summary - Sep 28, 07:00 PM EDT"


def test_parse_thread_detail_handles_missing_ai_summary():
    html = "<html><body><div>Price: $10.00</div><div>Original Price: $20.00</div></body></html>"
    detail = parse_thread_detail(html)
    assert detail.ai_summary_points == []
    assert detail.ai_summary_label is None
    assert detail.price == 10.00


# ---------------------------------------------------------------- search / related deals


def test_parse_search_results_filters_to_expired_only():
    results = parse_search_results(_read("rfd_search_sample.html").decode())
    # 4 rows in fixture, 1 is "Hot Deals" (not expired) and should be excluded
    assert len(results) == 3
    assert all(r.forum == "Expired Hot Deals" for r in results)


def test_parse_search_results_excludes_current_thread():
    results = parse_search_results(_read("rfd_search_sample.html").decode(), exclude_thread_id=2765412)
    ids_in_urls = [r.url for r in results]
    assert not any("2765412" in u for u in ids_in_urls)
    assert len(results) == 2


def test_parse_search_results_respects_limit():
    results = parse_search_results(_read("rfd_search_sample.html").decode(), limit=1)
    assert len(results) == 1


def test_normalize_search_terms_strips_price_and_noise_words():
    terms = _normalize_search_terms("[Costco] Level Ground Coffee $48.99 after $15 off")
    assert "48.99" not in terms
    assert "15" not in terms
    assert "after" not in terms.lower()
    assert "Level" in terms and "Ground" in terms and "Coffee" in terms


if __name__ == "__main__":
    import inspect
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_") and inspect.isfunction(obj)]
    passed, failed = 0, 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
            passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    raise SystemExit(1 if failed else 0)
