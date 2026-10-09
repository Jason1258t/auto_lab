"""Text clean-up of deep research 1.3.0: joined marks, JSON paragraphs."""

from autolab_engine.kinds.deep import split_marks, unwrap_json


def test_split_marks() -> None:
    assert split_marks("Blue [3, 5]. Red [7,8].") == "Blue [3][5]. Red [7][8]."


def test_unwrap_json() -> None:
    assert unwrap_json('{"text": "Reranking helps.", "citation": [13]}') == "Reranking helps. [13]"
    assert unwrap_json('{"text": "Reranking helps.", "linking_facts": ["26", "[27]"]}') == (
        "Reranking helps. [26][27]"
    )
    # A mark already in the text is not added again.
    assert (
        unwrap_json('{"text": "Reranking helps [13].", "facts": [13]}') == "Reranking helps [13]."
    )
    assert unwrap_json("Plain text [1].") == "Plain text [1]."
    assert unwrap_json('{"other": 1}') == '{"other": 1}'
