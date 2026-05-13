"""Tests for src/analyzers/source_attribution.py and ai_platform_response.py."""

from src.analyzers.source_attribution import SourceRow, build_source_attribution
from src.analyzers.ai_platform_response import build_ai_platform_response
from src.analyzers.sentiment_cooccurrence import build_sentiment_cooccurrence
from src.analyzers.benchmarking import build_benchmarking
from src.matchers import LabeledChat
from src.peec_client import Chat
from src.prompt_library import PromptEntry


def _chat(chat_id: str, sources: list[str], model_channel: str = "ChatGPT") -> Chat:
    return Chat(
        id=chat_id,
        model="chatgpt-scraper",
        model_channel=model_channel,
        prompt="test prompt",
        response="test response",
        country="US",
        position=None,
        mentions=[],
        sources=sources,
        sentiment=None,
        created="2026-05-01",
    )


def _labeled(chat: Chat) -> LabeledChat:
    return LabeledChat(chat=chat, prompt_id="DB-01", category="Direct Brand Queries")


def test_source_attribution_deduplicates_urls_across_chats():
    url = "https://example.com/page"
    chats = [
        _labeled(_chat("ch_1", [url])),
        _labeled(_chat("ch_2", [url])),
        _labeled(_chat("ch_3", [url])),
    ]
    rows = build_source_attribution(chats)
    assert len(rows) == 1
    assert rows[0].source_url == url


def test_source_attribution_counts_citations_correctly():
    url_a = "https://a.com"
    url_b = "https://b.com"
    chats = [
        _labeled(_chat("ch_1", [url_a, url_b])),
        _labeled(_chat("ch_2", [url_a])),
        _labeled(_chat("ch_3", [url_a])),
    ]
    rows = build_source_attribution(chats)
    by_url = {r.source_url: r for r in rows}
    assert by_url[url_a].citation_count == 3
    assert by_url[url_b].citation_count == 1


def test_source_attribution_joins_platforms_alphabetically_unique():
    url = "https://example.com"
    chats = [
        _labeled(_chat("ch_1", [url], model_channel="Perplexity")),
        _labeled(_chat("ch_2", [url], model_channel="ChatGPT")),
        _labeled(_chat("ch_3", [url], model_channel="ChatGPT")),  # duplicate platform
    ]
    rows = build_source_attribution(chats)
    assert rows[0].platform_citations == "ChatGPT, Perplexity"


def test_source_attribution_sorts_by_count_desc_then_domain_asc():
    chats = [
        _labeled(_chat("ch_1", ["https://b.com"])),
        _labeled(_chat("ch_2", ["https://a.com", "https://b.com"])),
        _labeled(_chat("ch_3", ["https://a.com", "https://b.com"])),
    ]
    rows = build_source_attribution(chats)
    # b.com appears 3 times, a.com appears 2 times
    assert rows[0].domain == "b.com"
    assert rows[1].domain == "a.com"


def test_source_attribution_content_type_and_topic_always_empty():
    chats = [_labeled(_chat("ch_1", ["https://example.com"]))]
    rows = build_source_attribution(chats)
    assert rows[0].content_type == ""
    assert rows[0].topic == ""


def test_source_attribution_handles_urls_without_scheme():
    url = "example.com/some/path"
    chats = [_labeled(_chat("ch_1", [url]))]
    rows = build_source_attribution(chats)
    assert rows[0].domain == "example.com"


def test_source_attribution_returns_empty_list_when_no_chats():
    assert build_source_attribution([]) == []


def test_source_attribution_returns_empty_list_when_chats_have_no_sources():
    chats = [
        _labeled(_chat("ch_1", [])),
        _labeled(_chat("ch_2", [])),
    ]
    assert build_source_attribution(chats) == []


def test_source_attribution_skips_empty_string_urls_in_sources_list():
    chats = [_labeled(_chat("ch_1", ["", "https://real.com", ""]))]
    rows = build_source_attribution(chats)
    assert len(rows) == 1
    assert rows[0].source_url == "https://real.com"


# ---------------------------------------------------------------------------
# AI Platform Response Tracking tests
# ---------------------------------------------------------------------------

BRAND = "Babylon Tours"


def _apr_chat(
    chat_id: str,
    mentions: list[str] = None,
    response: str = "",
    position=None,
    sentiment=None,
    sources: list[str] = None,
    model_channel: str = "ChatGPT",
) -> Chat:
    return Chat(
        id=chat_id,
        model="chatgpt-scraper",
        model_channel=model_channel,
        prompt="test prompt",
        response=response,
        country="US",
        position=position,
        mentions=mentions or [],
        sources=sources or [],
        sentiment=sentiment,
        created="2026-05-01",
    )


def _apr_labeled(chat: Chat, prompt_id: str = "DB-01", category="Direct Brand Queries") -> LabeledChat:
    return LabeledChat(chat=chat, prompt_id=prompt_id, category=category)  # type: ignore[arg-type]


def _apr_library(prompt_id: str = "DB-01", text: str = "Test prompt", category="Direct Brand Queries") -> dict:
    return {prompt_id: PromptEntry(prompt_id=prompt_id, text=text, category=category, intent="", priority="")}  # type: ignore[arg-type]


def _get_rows(chats, brand=BRAND, library=None, category="Direct Brand Queries"):
    library = library or _apr_library()
    result = build_ai_platform_response(chats, library, brand)
    return result.get("ChatGPT", {}).get(category, [])


def test_apr_single_chat_brand_mentioned_returns_Y():
    chats = [_apr_labeled(_apr_chat("ch_1", mentions=[BRAND]))]
    rows = _get_rows(chats)
    assert rows[0].brand_mentioned == "Y"


def test_apr_single_chat_brand_not_mentioned_returns_N():
    chats = [_apr_labeled(_apr_chat("ch_1", mentions=["Other Brand"]))]
    rows = _get_rows(chats)
    assert rows[0].brand_mentioned == "N"


def test_apr_multi_chat_partial_mention_returns_Y_with_count():
    chats = [
        _apr_labeled(_apr_chat("ch_1", mentions=[BRAND])),
        _apr_labeled(_apr_chat("ch_2", mentions=["Other"])),
        _apr_labeled(_apr_chat("ch_3", mentions=[BRAND])),
    ]
    rows = _get_rows(chats)
    assert rows[0].brand_mentioned == "Y (2/3)"


def test_apr_multi_chat_zero_mentions_returns_N_with_zero():
    chats = [
        _apr_labeled(_apr_chat("ch_1", mentions=["Other"])),
        _apr_labeled(_apr_chat("ch_2", mentions=["Other"])),
    ]
    rows = _get_rows(chats)
    assert rows[0].brand_mentioned == "N (0/2)"


def test_apr_brand_match_via_mentions_list():
    chats = [_apr_labeled(_apr_chat("ch_1", mentions=["Babylon Tours Official"]))]
    rows = _get_rows(chats)
    assert rows[0].brand_mentioned == "Y"


def test_apr_brand_match_via_response_text_when_not_in_mentions():
    chats = [_apr_labeled(_apr_chat("ch_1", mentions=[], response="Babylon Tours is a great company"))]
    rows = _get_rows(chats)
    assert rows[0].brand_mentioned == "Y"


def test_apr_brand_match_is_case_insensitive():
    chats = [_apr_labeled(_apr_chat("ch_1", mentions=["babylon tours"]))]
    rows = _get_rows(chats)
    assert rows[0].brand_mentioned == "Y"


def test_apr_position_average_only_includes_chats_with_brand_mentioned():
    chats = [
        _apr_labeled(_apr_chat("ch_1", mentions=[BRAND], position=2)),
        _apr_labeled(_apr_chat("ch_2", mentions=[BRAND], position=4)),
        _apr_labeled(_apr_chat("ch_3", mentions=[], position=1)),   # not mentioned — excluded
    ]
    rows = _get_rows(chats)
    assert rows[0].position == "3.0"


def test_apr_position_returns_dash_when_no_qualifying_chats():
    chats = [_apr_labeled(_apr_chat("ch_1", mentions=[], position=1))]
    rows = _get_rows(chats)
    assert rows[0].position == "-"


def test_apr_sentiment_average_only_includes_chats_with_brand_mentioned():
    chats = [
        _apr_labeled(_apr_chat("ch_1", mentions=[BRAND], sentiment=80.0)),
        _apr_labeled(_apr_chat("ch_2", mentions=[BRAND], sentiment=70.0)),
        _apr_labeled(_apr_chat("ch_3", mentions=[], sentiment=10.0)),  # excluded
    ]
    rows = _get_rows(chats)
    assert rows[0].sentiment_score == "75.0"


def test_apr_sentiment_label_positive_neutral_negative_no_sentiment():
    def _rows_with_sent(sent):
        chats = [_apr_labeled(_apr_chat("ch_1", mentions=[BRAND], sentiment=sent))]
        return _get_rows(chats)

    assert _rows_with_sent(80.0)[0].sentiment_label == "Positive"   # >= 60
    assert _rows_with_sent(50.0)[0].sentiment_label == "Neutral"    # 40 < x < 60
    assert _rows_with_sent(30.0)[0].sentiment_label == "Negative"   # <= 40

    chats = [_apr_labeled(_apr_chat("ch_1", mentions=[]))]
    assert _get_rows(chats)[0].sentiment_label == "No Sentiment"


def test_apr_co_mentions_excludes_brand_name_and_variants():
    chats = [_apr_labeled(_apr_chat("ch_1", mentions=[BRAND, "babylon", "Competitor A"]))]
    rows = _get_rows(chats)
    co = rows[0].co_mentions
    assert "Babylon" not in co
    assert "babylon" not in co
    assert "Competitor A" in co


def test_apr_co_mentions_sorted_by_count_then_name():
    chats = [
        _apr_labeled(_apr_chat("ch_1", mentions=["Alpha", "Beta", "Gamma"])),
        _apr_labeled(_apr_chat("ch_2", mentions=["Beta", "Gamma"])),
        _apr_labeled(_apr_chat("ch_3", mentions=["Gamma"])),
    ]
    rows = _get_rows(chats)
    # Gamma: 3, Beta: 2, Alpha: 1
    assert rows[0].co_mentions.startswith("Gamma (3/3), Beta (2/3), Alpha (1/3)")


def test_apr_co_mentions_caps_at_5():
    mentions = [f"Brand{i}" for i in range(8)]
    chats = [_apr_labeled(_apr_chat("ch_1", mentions=mentions))]
    rows = _get_rows(chats)
    # Should have at most 5 entries
    assert rows[0].co_mentions.count(",") <= 4


def test_apr_co_mentions_returns_None_when_empty():
    chats = [_apr_labeled(_apr_chat("ch_1", mentions=[]))]
    rows = _get_rows(chats)
    assert rows[0].co_mentions == "None"


def test_apr_sources_dedupes_and_caps_at_max():
    from src.config import MAX_SOURCES_PER_GROUP
    # 15 unique URLs across chats — should cap at MAX_SOURCES_PER_GROUP (10)
    chats = [
        _apr_labeled(_apr_chat(f"ch_{i}", sources=[f"https://url{i}.com"]))
        for i in range(15)
    ]
    rows = _get_rows(chats)
    assert rows[0].sources_citations.count("\n") == MAX_SOURCES_PER_GROUP - 1


def test_apr_sources_returns_dash_when_empty():
    chats = [_apr_labeled(_apr_chat("ch_1", sources=[]))]
    rows = _get_rows(chats)
    assert rows[0].sources_citations == "-"


def test_apr_chat_snapshot_picks_first_brand_mentioning_chat():
    chats = [
        _apr_labeled(_apr_chat("ch_1", response="No mention here")),
        _apr_labeled(_apr_chat("ch_2", mentions=[BRAND], response="Babylon Tours is great")),
    ]
    rows = _get_rows(chats)
    assert "Babylon Tours is great" in rows[0].chat_snapshot


def test_apr_chat_snapshot_falls_back_to_first_chat():
    chats = [_apr_labeled(_apr_chat("ch_1", response="Fallback response"))]
    rows = _get_rows(chats)
    assert "Fallback response" in rows[0].chat_snapshot


def test_apr_chat_snapshot_truncates_with_ellipsis():
    from src.config import CHAT_SNAPSHOT_CHARS
    long_response = "x" * (CHAT_SNAPSHOT_CHARS + 50)
    chats = [_apr_labeled(_apr_chat("ch_1", mentions=[BRAND], response=long_response))]
    rows = _get_rows(chats)
    assert rows[0].chat_snapshot.endswith("...")
    assert len(rows[0].chat_snapshot) == CHAT_SNAPSHOT_CHARS + 3


def test_apr_excludes_non_chatgpt_platforms():
    chats = [
        _apr_labeled(_apr_chat("ch_1", model_channel="Perplexity")),
        _apr_labeled(_apr_chat("ch_2", model_channel="Google AI Overview")),
    ]
    result = build_ai_platform_response(chats, _apr_library(), BRAND)
    assert "ChatGPT" not in result
    assert "Perplexity" not in result


def test_apr_categories_always_DB_CB_CO_order():
    chats = [_apr_labeled(_apr_chat("ch_1"))]
    result = build_ai_platform_response(chats, _apr_library(), BRAND)
    categories = list(result.get("ChatGPT", {}).keys())
    assert categories == ["Direct Brand Queries", "Category-Based Queries", "Comparison Queries"]


def test_apr_rows_sorted_by_prompt_id_numerically():
    library = {
        "DB-2": PromptEntry("DB-2", "Prompt 2", "Direct Brand Queries", "", ""),
        "DB-10": PromptEntry("DB-10", "Prompt 10", "Direct Brand Queries", "", ""),
    }
    chats = [
        _apr_labeled(_apr_chat("ch_1"), prompt_id="DB-10"),
        _apr_labeled(_apr_chat("ch_2"), prompt_id="DB-2"),
    ]
    result = build_ai_platform_response(chats, library, BRAND)
    rows = result["ChatGPT"]["Direct Brand Queries"]
    assert rows[0].prompt_id == "DB-2"
    assert rows[1].prompt_id == "DB-10"


def test_apr_context_analysis_and_notes_always_empty():
    chats = [_apr_labeled(_apr_chat("ch_1"))]
    rows = _get_rows(chats)
    assert rows[0].context_analysis == ""
    assert rows[0].notes == ""


def test_apr_no_row_emitted_for_prompts_without_chats():
    # prompt_library has DB-01 and DB-02, but only DB-01 has chats
    library = {
        "DB-01": PromptEntry("DB-01", "Prompt 1", "Direct Brand Queries", "", ""),
        "DB-02": PromptEntry("DB-02", "Prompt 2", "Direct Brand Queries", "", ""),
    }
    chats = [_apr_labeled(_apr_chat("ch_1"), prompt_id="DB-01")]
    result = build_ai_platform_response(chats, library, BRAND)
    rows = result["ChatGPT"]["Direct Brand Queries"]
    assert len(rows) == 1
    assert rows[0].prompt_id == "DB-01"


# ---------------------------------------------------------------------------
# Sentiment & Co-Occurrence tests
# ---------------------------------------------------------------------------

def _sc_chat(
    chat_id: str,
    mentions: list[str] = None,
    response: str = "",
    sentiment=None,
    model_channel: str = "ChatGPT",
) -> Chat:
    return Chat(
        id=chat_id, model="chatgpt-scraper", model_channel=model_channel,
        prompt="test prompt", response=response, country="US",
        position=None, mentions=mentions or [], sources=[],
        sentiment=sentiment, created="2026-05-01",
    )


def _sc_labeled(chat: Chat, prompt_id: str = "DB-01", category="Direct Brand Queries") -> LabeledChat:
    return LabeledChat(chat=chat, prompt_id=prompt_id, category=category)  # type: ignore[arg-type]


def _sc_library(**kwargs) -> dict:
    lib = {}
    for pid, (text, cat) in kwargs.items():
        lib[pid] = PromptEntry(pid, text, cat, "", "")  # type: ignore[arg-type]
    return lib


def _sc(chats, brand=BRAND, library=None):
    library = library or _sc_library(**{"DB-01": ("Test prompt", "Direct Brand Queries")})
    return build_sentiment_cooccurrence(chats, library, brand)


def test_sc_summary_mention_rate_format():
    chats = [
        _sc_labeled(_sc_chat("ch_1", mentions=[BRAND], sentiment=80.0)),
        _sc_labeled(_sc_chat("ch_2", mentions=[BRAND], sentiment=70.0)),
    ]
    summary, _, _ = _sc(chats)
    db_row = next(r for r in summary if r.category == "Direct Brand Queries")
    assert db_row.mention_rate == "1/1 (100%)"


def test_sc_summary_mention_rate_zero_total():
    summary, _, _ = _sc([])
    db_row = next(r for r in summary if r.category == "Direct Brand Queries")
    assert db_row.mention_rate == "0/0 (—)"


def test_sc_summary_avg_sentiment_aggregates_across_platforms():
    chats = [
        _sc_labeled(_sc_chat("ch_1", mentions=[BRAND], sentiment=80.0, model_channel="ChatGPT")),
        _sc_labeled(_sc_chat("ch_2", mentions=[BRAND], sentiment=60.0, model_channel="Perplexity")),
    ]
    summary, _, _ = _sc(chats)
    overall = next(r for r in summary if r.category == "OVERALL")
    assert overall.avg_sentiment_score == "70.0"


def test_sc_summary_avg_sentiment_excludes_chats_without_brand_mention():
    chats = [
        _sc_labeled(_sc_chat("ch_1", mentions=[BRAND], sentiment=80.0)),
        _sc_labeled(_sc_chat("ch_2", mentions=[], sentiment=20.0)),  # excluded
    ]
    summary, _, _ = _sc(chats)
    db_row = next(r for r in summary if r.category == "Direct Brand Queries")
    assert db_row.avg_sentiment_score == "80.0"


def test_sc_summary_overall_row_recomputes_from_scratch():
    library = _sc_library(
        **{
            "DB-01": ("DB prompt", "Direct Brand Queries"),
            "CB-01": ("CB prompt", "Category-Based Queries"),
        }
    )
    chats = [
        _sc_labeled(_sc_chat("ch_1", mentions=[BRAND], sentiment=80.0), prompt_id="DB-01"),
        _sc_labeled(_sc_chat("ch_2", mentions=[BRAND], sentiment=60.0), prompt_id="CB-01",
                    category="Category-Based Queries"),
    ]
    summary, _, _ = build_sentiment_cooccurrence(chats, library, BRAND)
    overall = next(r for r in summary if r.category == "OVERALL")
    assert overall.total_prompts == 2
    assert overall.brand_mentioned_count == 2
    assert overall.avg_sentiment_score == "70.0"


def test_sc_summary_positive_neutral_negative_counts_use_per_prompt_avg():
    library = _sc_library(**{
        "DB-01": ("P1", "Direct Brand Queries"),
        "DB-02": ("P2", "Direct Brand Queries"),
        "DB-03": ("P3", "Direct Brand Queries"),
    })
    chats = [
        _sc_labeled(_sc_chat("ch_1", mentions=[BRAND], sentiment=80.0), prompt_id="DB-01"),
        _sc_labeled(_sc_chat("ch_2", mentions=[BRAND], sentiment=50.0), prompt_id="DB-02"),
        _sc_labeled(_sc_chat("ch_3", mentions=[BRAND], sentiment=30.0), prompt_id="DB-03"),
    ]
    summary, _, _ = build_sentiment_cooccurrence(chats, library, BRAND)
    db_row = next(r for r in summary if r.category == "Direct Brand Queries")
    assert db_row.positive_count == 1
    assert db_row.neutral_count == 1
    assert db_row.negative_count == 1


def test_sc_summary_prompts_without_qualifying_chats_dont_count():
    chats = [_sc_labeled(_sc_chat("ch_1", mentions=[], sentiment=80.0))]
    summary, _, _ = _sc(chats)
    db_row = next(r for r in summary if r.category == "Direct Brand Queries")
    assert db_row.positive_count == 0
    assert db_row.neutral_count == 0
    assert db_row.negative_count == 0


def test_sc_cooccurrence_excludes_brand_and_variants():
    chats = [_sc_labeled(_sc_chat("ch_1", mentions=[BRAND, "babylon", "Competitor A"]))]
    _, coocc, _ = _sc(chats)
    entities = [r.brand_or_entity for r in coocc]
    assert "babylon" not in entities
    assert BRAND not in entities
    assert "Competitor A" in entities


def test_sc_cooccurrence_counts_once_per_chat_not_per_mention_occurrence():
    # "Competitor A" appears in two chats — count should be 2
    chats = [
        _sc_labeled(_sc_chat("ch_1", mentions=["Competitor A", "Competitor A"])),
        _sc_labeled(_sc_chat("ch_2", mentions=["Competitor A"])),
    ]
    _, coocc, _ = _sc(chats)
    row = next(r for r in coocc if r.brand_or_entity == "Competitor A")
    assert row.cooccurrence_count == 2


def test_sc_cooccurrence_sorted_by_count_then_name():
    chats = [
        _sc_labeled(_sc_chat("ch_1", mentions=["Alpha", "Beta", "Gamma"])),
        _sc_labeled(_sc_chat("ch_2", mentions=["Beta", "Gamma"])),
        _sc_labeled(_sc_chat("ch_3", mentions=["Gamma"])),
    ]
    _, coocc, _ = _sc(chats)
    assert coocc[0].brand_or_entity == "Gamma"
    assert coocc[1].brand_or_entity == "Beta"
    assert coocc[2].brand_or_entity == "Alpha"


def test_sc_cooccurrence_capped_at_max():
    from src.config import MAX_COOCCURRENCE_ROWS
    mentions = [f"Brand{i}" for i in range(MAX_COOCCURRENCE_ROWS + 5)]
    chats = [_sc_labeled(_sc_chat("ch_1", mentions=mentions))]
    _, coocc, _ = _sc(chats)
    assert len(coocc) == MAX_COOCCURRENCE_ROWS


def test_sc_detailed_one_row_per_prompt_id_across_platforms():
    chats = [
        _sc_labeled(_sc_chat("ch_1", model_channel="ChatGPT")),
        _sc_labeled(_sc_chat("ch_2", model_channel="Perplexity")),
    ]
    _, _, detailed = _sc(chats)
    assert len(detailed) == 1
    assert detailed[0].prompt_id == "DB-01"


def test_sc_detailed_sorted_by_category_then_numeric_prompt_id():
    library = _sc_library(**{
        "DB-2": ("DB-2", "Direct Brand Queries"),
        "DB-10": ("DB-10", "Direct Brand Queries"),
        "CB-01": ("CB-01", "Category-Based Queries"),
    })
    chats = [
        _sc_labeled(_sc_chat("ch_1"), prompt_id="DB-10"),
        _sc_labeled(_sc_chat("ch_2"), prompt_id="CB-01", category="Category-Based Queries"),
        _sc_labeled(_sc_chat("ch_3"), prompt_id="DB-2"),
    ]
    _, _, detailed = build_sentiment_cooccurrence(chats, library, BRAND)
    ids = [r.prompt_id for r in detailed]
    assert ids == ["DB-2", "DB-10", "CB-01"]


def test_sc_detailed_brand_mentioned_format_Yes_or_No():
    chats = [
        _sc_labeled(_sc_chat("ch_1", mentions=[BRAND])),
        _sc_labeled(_sc_chat("ch_2", mentions=[])),
    ]
    _, _, detailed = _sc(chats)
    assert detailed[0].brand_mentioned == "Yes (1/2)"

    chats2 = [_sc_labeled(_sc_chat("ch_1", mentions=[]))]
    _, _, detailed2 = _sc(chats2)
    assert detailed2[0].brand_mentioned == "No (0/1)"


def test_sc_detailed_sentiment_label_with_no_data():
    chats = [_sc_labeled(_sc_chat("ch_1", mentions=[], sentiment=None))]
    _, _, detailed = _sc(chats)
    assert detailed[0].sentiment_label == "No Sentiment"
    assert detailed[0].sentiment_score == "-"


def test_sc_judgment_fields_always_empty():
    chats = [
        _sc_labeled(_sc_chat("ch_1", mentions=["Competitor"])),
        _sc_labeled(_sc_chat("ch_2", mentions=[BRAND], sentiment=70.0)),
    ]
    _, coocc, detailed = _sc(chats)
    assert coocc[0].relationship_type == ""
    assert coocc[0].typical_position == ""
    assert coocc[0].key_associations == ""
    assert coocc[0].opportunity_threat == ""
    assert detailed[0].key_observations == ""


# ---------------------------------------------------------------------------
# Benchmarking tests
# ---------------------------------------------------------------------------

def _bm_chat(
    chat_id: str,
    mentions: list[str] = None,
    response: str = "",
    position=None,
    sentiment=None,
) -> Chat:
    return Chat(
        id=chat_id, model="chatgpt-scraper", model_channel="ChatGPT",
        prompt="test", response=response, country="US",
        position=position, mentions=mentions or [], sources=[],
        sentiment=sentiment, created="2026-05-01",
    )


def _bm_labeled(chat: Chat, prompt_id: str = "DB-01", category="Direct Brand Queries") -> LabeledChat:
    return LabeledChat(chat=chat, prompt_id=prompt_id, category=category)  # type: ignore[arg-type]


def _bm_library(**kwargs) -> dict:
    lib = {}
    for pid, (text, cat) in kwargs.items():
        lib[pid] = PromptEntry(pid, text, cat, "", "")  # type: ignore[arg-type]
    return lib


def _bm(chats, brand=BRAND, library=None):
    library = library or _bm_library(**{"DB-01": ("Test", "Direct Brand Queries")})
    return build_benchmarking(chats, library, brand)


def test_bm_focal_brand_always_first_row_in_each_category():
    chats = [
        _bm_labeled(_bm_chat("ch_1", mentions=[BRAND, "Competitor A"])),
    ]
    result = _bm(chats)
    assert result["Direct Brand Queries"][0].brand == BRAND


def test_bm_competitors_sorted_by_count_then_name():
    chats = [
        _bm_labeled(_bm_chat("ch_1", mentions=["Alpha", "Beta", "Gamma"])),
        _bm_labeled(_bm_chat("ch_2", mentions=["Beta", "Gamma"])),
        _bm_labeled(_bm_chat("ch_3", mentions=["Gamma"])),
    ]
    result = _bm(chats)
    rows = result["Direct Brand Queries"]
    brands = [r.brand for r in rows[1:]]
    assert brands == ["Gamma", "Beta", "Alpha"]


def test_bm_caps_competitors_at_max():
    from src.config import MAX_COMPETITORS_PER_BENCHMARK
    mentions = [f"Comp{i}" for i in range(MAX_COMPETITORS_PER_BENCHMARK + 3)]
    chats = [_bm_labeled(_bm_chat("ch_1", mentions=mentions))]
    result = _bm(chats)
    rows = result["Direct Brand Queries"]
    # focal brand + at most MAX_COMPETITORS_PER_BENCHMARK competitors
    assert len(rows) <= MAX_COMPETITORS_PER_BENCHMARK + 1


def test_bm_mention_rate_denominator_is_prompts_not_chats():
    library = _bm_library(**{
        "DB-01": ("P1", "Direct Brand Queries"),
        "DB-02": ("P2", "Direct Brand Queries"),
    })
    chats = [
        _bm_labeled(_bm_chat("ch_1", mentions=[BRAND]), prompt_id="DB-01"),
        _bm_labeled(_bm_chat("ch_2", mentions=[BRAND]), prompt_id="DB-01"),  # same prompt
        _bm_labeled(_bm_chat("ch_3", mentions=[]), prompt_id="DB-02"),
    ]
    result = build_benchmarking(chats, library, BRAND)
    focal = result["Direct Brand Queries"][0]
    # 1 distinct prompt mentioned out of 2 total
    assert focal.mention_rate == "1/2 (50%)"


def test_bm_focal_brand_uses_response_text_fallback_for_matching():
    chats = [
        _bm_labeled(_bm_chat("ch_1", mentions=[], response=f"{BRAND} is great")),
    ]
    result = _bm(chats)
    focal = result["Direct Brand Queries"][0]
    assert focal.mention_rate == "1/1 (100%)"


def test_bm_competitors_match_only_via_mentions_list():
    chats = [
        _bm_labeled(_bm_chat("ch_1", mentions=[], response="Competitor A is great")),
    ]
    result = _bm(chats)
    rows = result["Direct Brand Queries"]
    brands = [r.brand for r in rows]
    assert "Competitor A" not in brands


def test_bm_avg_position_skips_none_values():
    chats = [
        _bm_labeled(_bm_chat("ch_1", mentions=[BRAND], position=2)),
        _bm_labeled(_bm_chat("ch_2", mentions=[BRAND], position=4)),
        _bm_labeled(_bm_chat("ch_3", mentions=[BRAND], position=None)),
    ]
    result = _bm(chats)
    assert result["Direct Brand Queries"][0].avg_position == "3.0"


def test_bm_avg_position_returns_dash_when_no_data():
    chats = [_bm_labeled(_bm_chat("ch_1", mentions=[BRAND], position=None))]
    result = _bm(chats)
    assert result["Direct Brand Queries"][0].avg_position == "-"


def test_bm_avg_sentiment_returns_dash_when_no_data():
    chats = [_bm_labeled(_bm_chat("ch_1", mentions=[BRAND], sentiment=None))]
    result = _bm(chats)
    assert result["Direct Brand Queries"][0].avg_sentiment == "-"


def test_bm_zero_data_category_still_returns_focal_brand_row():
    chats = []
    result = _bm(chats)
    db_rows = result["Direct Brand Queries"]
    assert len(db_rows) == 1
    assert db_rows[0].brand == BRAND
    assert db_rows[0].mention_rate == "0/0 (—)"
    assert db_rows[0].avg_position == "-"
    assert db_rows[0].avg_sentiment == "-"


def test_bm_brand_excluded_from_competitor_list():
    chats = [
        _bm_labeled(_bm_chat("ch_1", mentions=[BRAND, "babylon", "Competitor A"])),
    ]
    result = _bm(chats)
    brands = [r.brand for r in result["Direct Brand Queries"]]
    assert BRAND not in brands[1:]
    assert "babylon" not in brands


def test_bm_all_three_categories_always_returned():
    result = _bm([])
    assert set(result.keys()) == {"Direct Brand Queries", "Category-Based Queries", "Comparison Queries"}


def test_bm_dominant_themes_always_empty():
    chats = [_bm_labeled(_bm_chat("ch_1", mentions=[BRAND, "Competitor"]))]
    result = _bm(chats)
    for row in result["Direct Brand Queries"]:
        assert row.dominant_themes == ""


def test_bm_competitor_counted_once_per_chat_not_per_mention_occurrence():
    chats = [
        _bm_labeled(_bm_chat("ch_1", mentions=["Competitor A", "Competitor A"])),
        _bm_labeled(_bm_chat("ch_2", mentions=["Competitor A"])),
    ]
    result = _bm(chats)
    comp_row = next(r for r in result["Direct Brand Queries"] if r.brand == "Competitor A")
    # 2 chats mention it — mention_rate denominator is 1 prompt
    assert comp_row.mention_rate == "1/1 (100%)"


# ---------------------------------------------------------------------------
# Cross-analyzer edge cases
# ---------------------------------------------------------------------------

def test_all_analyzers_handle_empty_chat_list():
    """Each analyzer returns empty/zero-state output without exceptions."""
    apr = build_ai_platform_response([], {}, BRAND)
    assert apr == {}

    sa = build_source_attribution([])
    assert sa == []

    summary, coocc, detailed = build_sentiment_cooccurrence([], {}, BRAND)
    assert len(summary) == 4  # 3 categories + OVERALL, all zero
    assert coocc == []
    assert detailed == []

    bm = build_benchmarking([], {}, BRAND)
    assert set(bm.keys()) == {"Direct Brand Queries", "Category-Based Queries", "Comparison Queries"}
    for rows in bm.values():
        assert rows[0].brand == BRAND
        assert rows[0].mention_rate == "0/0 (—)"


def test_all_analyzers_handle_prompt_library_with_one_category_empty():
    """Zero entries in Comparison Queries; other categories work normally."""
    library = {"DB-01": PromptEntry("DB-01", "Prompt 1", "Direct Brand Queries", "", "")}
    chats = [_apr_labeled(_apr_chat("ch_1", mentions=[BRAND]))]

    apr = build_ai_platform_response(chats, library, BRAND)
    assert apr["ChatGPT"]["Comparison Queries"] == []
    assert len(apr["ChatGPT"]["Direct Brand Queries"]) == 1

    bm = build_benchmarking(chats, library, BRAND)
    assert bm["Comparison Queries"][0].mention_rate == "0/0 (—)"


def test_apr_chat_with_empty_mentions_and_brand_in_response():
    """Response-text fallback still counts as brand mentioned when mentions is empty."""
    chats = [_apr_labeled(_apr_chat("ch_1", mentions=[], response=f"{BRAND} is great"))]
    rows = _get_rows(chats)
    assert rows[0].brand_mentioned == "Y"


def test_apr_chat_with_sentiment_exactly_zero():
    """Sentiment of 0.0 is a real score, not treated as None."""
    chats = [_apr_labeled(_apr_chat("ch_1", mentions=[BRAND], sentiment=0.0))]
    rows = _get_rows(chats)
    assert rows[0].sentiment_score == "0.0"
    assert rows[0].sentiment_label == "Negative"


def test_sc_handles_chats_with_no_sources():
    """Co-occurrence and summary produce sensible output even with no sources."""
    chats = [_sc_labeled(_sc_chat("ch_1", mentions=["Competitor A"]))]
    summary, coocc, detailed = _sc(chats)
    assert len(coocc) == 1
    assert coocc[0].brand_or_entity == "Competitor A"
    assert all(r.total_prompts >= 0 for r in summary)


def test_bm_handles_category_where_focal_brand_has_zero_chats():
    """A category with no chats for focal brand still emits a 0/0 (—) row."""
    library = _bm_library(**{
        "DB-01": ("DB", "Direct Brand Queries"),
        "CB-01": ("CB", "Category-Based Queries"),
    })
    chats = [_bm_labeled(_bm_chat("ch_1", mentions=[BRAND]), prompt_id="DB-01")]
    result = build_benchmarking(chats, library, BRAND)
    cb_rows = result["Category-Based Queries"]
    assert cb_rows[0].brand == BRAND
    assert cb_rows[0].mention_rate == "0/0 (—)"
    assert cb_rows[0].avg_position == "-"
