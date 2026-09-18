from __future__ import annotations

from app.application.voice.sentence_splitter import StreamingSentenceSplitter


def test_streaming_sentence_splitter_basic() -> None:
    splitter = StreamingSentenceSplitter(min_sentence_chars=10)
    tokens = ["Chào ", "bạn. ", "Hôm ", "nay ", "bạn ", "thấy ", "thế ", "nào?"]
    sentences = []
    for t in tokens:
        for s in splitter.feed(t):
            sentences.append(s)

    for s in splitter.flush():
        sentences.append(s)

    assert len(sentences) == 2
    assert sentences[0] == (0, "Chào bạn.")
    assert sentences[1] == (1, "Hôm nay bạn thấy thế nào?")


def test_streaming_sentence_splitter_ignores_decimals_and_abbreviations() -> None:
    splitter = StreamingSentenceSplitter(min_sentence_chars=15)
    tokens = ["Phiên ", "bản ", "PostgreSQL ", "16.4 ", "rất ", "ổn ", "định. ", "Đúng ", "không?"]
    sentences = []
    for t in tokens:
        for s in splitter.feed(t):
            sentences.append(s)
    for s in splitter.flush():
        sentences.append(s)

    assert len(sentences) == 2
    assert "16.4" in sentences[0][1]
    assert sentences[0][1] == "Phiên bản PostgreSQL 16.4 rất ổn định."
    assert sentences[1][1] == "Đúng không?"


def test_streaming_sentence_splitter_flush_incomplete() -> None:
    splitter = StreamingSentenceSplitter(min_sentence_chars=10)
    for s in splitter.feed("Tôi đang suy nghĩ"):
        pass
    leftover = list(splitter.flush())
    assert len(leftover) == 1
    assert leftover[0] == (0, "Tôi đang suy nghĩ")
