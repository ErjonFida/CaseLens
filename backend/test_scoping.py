from config import Settings
from vector_store import LegalVectorStore as Store

NAMED = [(7, 1.01, "scoutcam agreement"), (3, 0.01, "agreement"), (9, 0.01, "agreement")]


def test_title_span_removed():
    q = "Which law governs the Alliance Bancorp Inc. of Pennsylvania agreement?"
    matched = {"alliance", "bancorp", "inc", "pennsylvania", "agreement"}
    assert Store._strip_title(q, matched) == "Which law governs the"


def test_topic_word_keeps_its_own_mention():
    q = "What are the termination terms in the Acme Termination Agreement?"
    assert Store._strip_title(q, {"acme", "termination", "agreement"}) == "What are the termination terms in the"


def test_unscoped_query_untouched():
    q = "What does section 2 talk about?"
    assert Store._strip_title(q, set()) == q


def test_never_strips_to_nothing():
    q = "Acme agreement?"
    assert Store._strip_title(q, {"acme", "agreement"}) == q


def test_selection_narrows_to_the_named_document():
    assert Store._pick_document(NAMED, candidates=[3, 7, 9])[0] == 7


def test_selection_naming_none_picks_none():
    assert Store._pick_document(NAMED[1:], candidates=[3, 9]) is None


def test_a_name_outside_the_selection_cannot_escape_it():
    assert Store._pick_document(NAMED, candidates=[3, 9]) is None


def test_whole_document_off_for_ollama_and_bounded_by_its_window():
    unset = {"WHOLE_DOCUMENT_MAX_TOKENS": None}
    assert Settings(LLM_PROVIDER="ollama", **unset).whole_document_max_tokens == 0
    assert Settings(LLM_PROVIDER="gemini", **unset).whole_document_max_tokens == 40_000
    capped = Settings(LLM_PROVIDER="ollama", LLM_NUM_CTX=8192, WHOLE_DOCUMENT_MAX_TOKENS=100_000)
    assert capped.whole_document_max_tokens == 4915


if __name__ == "__main__":
    test_title_span_removed()
    test_topic_word_keeps_its_own_mention()
    test_unscoped_query_untouched()
    test_never_strips_to_nothing()
    test_selection_narrows_to_the_named_document()
    test_selection_naming_none_picks_none()
    test_a_name_outside_the_selection_cannot_escape_it()
    test_whole_document_off_for_ollama_and_bounded_by_its_window()
    print("ok")
