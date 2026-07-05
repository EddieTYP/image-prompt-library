from backend.services.search_query import parse_item_search_query


def test_plain_keyword_search_stays_plain():
    parsed = parse_item_search_query("apple packaging")
    assert parsed.keyword == "apple packaging"
    assert parsed.created is None
    assert parsed.updated is None
    assert parsed.tags == []
    assert parsed.collections == []
    assert parsed.models == []
    assert parsed.sources == []
    assert parsed.favorite is None
    assert parsed.has == set()


def test_supported_filters_are_removed_from_keyword_text():
    parsed = parse_item_search_query("created:7d tag:template source:awesome packaging")
    assert parsed.keyword == "packaging"
    assert parsed.created == "7d"
    assert parsed.tags == ["template"]
    assert parsed.sources == ["awesome"]


def test_commas_are_optional_separators():
    parsed = parse_item_search_query("created:today, apple")
    assert parsed.keyword == "apple"
    assert parsed.created == "today"


def test_unknown_keys_remain_keywords():
    parsed = parse_item_search_query("creator:edward apple")
    assert parsed.keyword == "creator:edward apple"
    assert parsed.tags == []


def test_boolean_and_has_filters():
    parsed = parse_item_search_query("fav:true has:image has:reference cat")
    assert parsed.keyword == "cat"
    assert parsed.favorite is True
    assert parsed.has == {"image", "reference"}


def test_invalid_filter_values_remain_keywords():
    parsed = parse_item_search_query("created:forever fav:maybe has:video apple")
    assert parsed.keyword == "created:forever fav:maybe has:video apple"
    assert parsed.created is None
    assert parsed.favorite is None
    assert parsed.has == set()
