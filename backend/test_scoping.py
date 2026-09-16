"""Title removal must take the document's name out of a scoped query and
nothing else - in particular not a topic word that also appears in the title."""
from vector_store import LegalVectorStore as Store


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


if __name__ == "__main__":
    test_title_span_removed()
    test_topic_word_keeps_its_own_mention()
    test_unscoped_query_untouched()
    test_never_strips_to_nothing()
    print("ok")
