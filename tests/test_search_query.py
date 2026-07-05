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
    assert parsed.archived is None
    assert parsed.has == set()


def test_supported_filters_are_removed_from_keyword_text():
    parsed = parse_item_search_query("created:7d tag:template source:awesome packaging")
    assert parsed.keyword == "packaging"
    assert parsed.created == "7d"
    assert parsed.tags == ["template"]
    assert parsed.sources == ["awesome"]


def test_all_supported_list_and_date_filters_are_parsed():
    parsed = parse_item_search_query(
        "created:30d updated:yesterday collection:ads model:gpt-image source:awesome apple"
    )
    assert parsed.keyword == "apple"
    assert parsed.created == "30d"
    assert parsed.updated == "yesterday"
    assert parsed.collections == ["ads"]
    assert parsed.models == ["gpt-image"]
    assert parsed.sources == ["awesome"]


def test_commas_are_optional_separators():
    parsed = parse_item_search_query("created:today, apple")
    assert parsed.keyword == "apple"
    assert parsed.created == "today"


def test_comma_separated_filters_are_parsed():
    parsed = parse_item_search_query("tag:a,tag:b apple")
    assert parsed.keyword == "apple"
    assert parsed.tags == ["a", "b"]


def test_list_filters_are_deduplicated_preserving_first_occurrence():
    parsed = parse_item_search_query("tag:a tag:b tag:a collection:x collection:x apple")
    assert parsed.keyword == "apple"
    assert parsed.tags == ["a", "b"]
    assert parsed.collections == ["x"]


def test_unknown_keys_remain_keywords():
    parsed = parse_item_search_query("creator:edward apple")
    assert parsed.keyword == "creator:edward apple"
    assert parsed.tags == []


def test_boolean_and_has_filters():
    parsed = parse_item_search_query(
        "fav:true favorite:false archived:true has:image has:result has:reference has:prompt cat"
    )
    assert parsed.keyword == "cat"
    assert parsed.favorite is False
    assert parsed.archived is True
    assert parsed.has == {"image", "result", "reference", "prompt"}


def test_invalid_filter_values_remain_keywords():
    parsed = parse_item_search_query(
        "created:forever updated:someday fav:maybe archived:maybe has:video apple"
    )
    assert parsed.keyword == "created:forever updated:someday fav:maybe archived:maybe has:video apple"
    assert parsed.created is None
    assert parsed.updated is None
    assert parsed.favorite is None
    assert parsed.archived is None
    assert parsed.has == set()
