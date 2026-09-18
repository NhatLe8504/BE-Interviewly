from __future__ import annotations

import re
from typing import Iterator

# Common abbreviations in English and Vietnamese that should not split sentences
ABBREVIATIONS = {
    "mr.", "ms.", "mrs.", "dr.", "prof.", "e.g.", "i.e.", "etc.", "vs.",
    "v.v.", "v/v", "tp.", "th.s", "ts.", "pgs.", "gs.", "đ/c", "k/g",
}

# Sentence ending punctuation patterns
SPLIT_REGEX = re.compile(r'([.!?\n\u3002\uff01\uff1f]+)(\s+|$)')


class StreamingSentenceSplitter:
    """
    Buffers tokens from an LLM stream and yields complete sentences as soon
    as sentence boundaries are detected. Emits the first complete sentence
    with minimal latency.
    """

    def __init__(self, min_sentence_chars: int = 8, min_words: int = 2) -> None:
        self.min_sentence_chars = min_sentence_chars
        self.min_words = min_words
        self._buffer: str = ""
        self._sentence_index: int = 0

    @property
    def sentence_index(self) -> int:
        return self._sentence_index

    def feed(self, token: str) -> Iterator[tuple[int, str]]:
        self._buffer += token

        while True:
            match = SPLIT_REGEX.search(self._buffer)
            if not match:
                break

            punct_end = match.end(1)
            candidate = self._buffer[:punct_end].strip()
            words = candidate.split()

            # Check if candidate ends with a digit before period (e.g., 3.14)
            if match.group(1) == "." and len(candidate) >= 2:
                char_before = candidate[-2] if len(candidate) >= 2 else ""
                rest_after = self._buffer[punct_end:]
                if char_before.isdigit() and rest_after and rest_after[0].isdigit():
                    # This is a decimal number like 3.14, do not split
                    break

            # Check for known abbreviation (e.g. "e.g.", "v.v.")
            last_word = words[-1].lower() if words else ""
            if last_word in ABBREVIATIONS:
                # Do not split on abbreviations
                break

            # Ensure minimal content before splitting
            if len(candidate) < self.min_sentence_chars and len(words) < self.min_words and "\n" not in match.group(1):
                break

            # We have a valid complete sentence
            sentence = candidate
            self._buffer = self._buffer[match.end():].lstrip()
            idx = self._sentence_index
            self._sentence_index += 1
            yield (idx, sentence)

    def flush(self) -> Iterator[tuple[int, str]]:
        leftover = self._buffer.strip()
        self._buffer = ""
        if leftover:
            idx = self._sentence_index
            self._sentence_index += 1
            yield (idx, leftover)
