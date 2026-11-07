import pytest

from chunker import chunk_text


def test_empty_text_returns_nothing():
    assert chunk_text("") == []
    assert chunk_text("  \n ") == []


def test_short_text_stays_whole():
    assert chunk_text("短文", 500, 100) == ["短文"]


def test_text_without_punctuation_falls_back_to_sliding_window():
    assert chunk_text("ABCDEFGHIJ", 5, 2) == ["ABCDE", "DEFGH", "GHIJ"]


def test_no_extra_chunk_when_window_ends_exactly():
    assert chunk_text("ABCDEFGH", 5, 2) == ["ABCDE", "DEFGH"]
    assert chunk_text("ABCDE", 5, 2) == ["ABCDE"]


def test_no_overlap_keeps_all_text():
    assert "".join(chunk_text("ABCDEFGHIJ", 3, 0)) == "ABCDEFGHIJ"


@pytest.mark.parametrize("size,overlap", [(5, 5), (5, 6), (5, -1), (0, 0)])
def test_invalid_arguments_are_rejected(size, overlap):
    with pytest.raises(ValueError):
        chunk_text("ABC", size, overlap)


def test_chunks_end_at_sentence_boundaries():
    text = "".join(f"第{i}句內容在這裡。" for i in range(100))
    chunks = chunk_text(text, 100, 20)
    assert len(chunks) > 1
    assert all(chunk.endswith("。") for chunk in chunks)


def test_every_sentence_is_kept_and_size_is_respected():
    sentences = [f"第{i}句內容在這裡。" for i in range(100)]
    chunks = chunk_text("".join(sentences), 100, 20)
    assert all(len(chunk) <= 100 for chunk in chunks)
    assert all(any(sentence in chunk for chunk in chunks) for sentence in sentences)


def test_overlap_repeats_whole_sentences():
    text = "".join(f"第{i}句內容在這裡。" for i in range(100))
    first, second = chunk_text(text, 100, 20)[:2]
    overlap = second[:second.index(first[-1 - len("第9句內容在這裡。"):]) + len("第9句內容在這裡。") + 1]
    assert first.endswith(overlap)
    assert overlap.endswith("。")
    assert len(overlap) <= 20


def test_long_sentence_is_split_at_commas():
    text = "，".join(["這是一段很長的子句內容"] * 30) + "。"
    chunks = chunk_text(text, 50, 0)
    assert len(chunks) > 1
    assert all(chunk.endswith(("，", "。")) for chunk in chunks)


def test_newline_counts_as_boundary():
    assert chunk_text("甲甲甲甲\n乙乙乙乙\n丙丙丙丙", 10, 0) == ["甲甲甲甲\n乙乙乙乙", "丙丙丙丙"]


def test_sentence_longer_than_overlap_still_makes_progress():
    text = "甲" * 40 + "。" + "乙" * 40 + "。" + "丙" * 40 + "。"
    assert len(chunk_text(text, 50, 45)) == 3
