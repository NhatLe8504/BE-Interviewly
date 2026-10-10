from __future__ import annotations

import re


def sanitize_spoken_text(text: str) -> str:
    """
    Sanitize text returned by LLMs before passing it to TTS synthesis,
    spoken subtitles, or interview timeline messages.

    Strips any accidental markdown syntax (bold, italics, headers, lists, code blocks,
    tables, etc.) so that the voice agent speaks and renders 100% natural conversational text.
    """
    if not text:
        return ""

    cleaned = text

    # 1. Remove markdown code blocks: ```lang ... ``` -> content
    cleaned = re.sub(r"```[\w-]*\s*([\s\S]*?)\s*```", r"\1", cleaned)

    # 2. Remove inline code backticks: `code` -> code
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)

    # 3. Remove images: ![alt](url) -> ""
    cleaned = re.sub(r"!\[([^\]]*)\]\([^)]+\)", "", cleaned)

    # 4. Remove links: [text](url) -> text
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)

    # 5. Remove bold & italic combinations: ***text*** or ___text___ -> text
    cleaned = re.sub(r"\*{3}([^*]+)\*{3}", r"\1", cleaned)
    cleaned = re.sub(r"_{3}([^_]+)_{3}", r"\1", cleaned)

    # 6. Remove bold: **text** or __text__ -> text
    cleaned = re.sub(r"\*{2}([^*]+)\*{2}", r"\1", cleaned)
    cleaned = re.sub(r"_{2}([^_]+)_{2}", r"\1", cleaned)

    # 7. Remove italics: *text* -> text
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"(^|\s)_([^_]+)_($|\s)", r"\1\2\3", cleaned)

    # 8. Remove markdown headers: #, ##, ### at line starts
    cleaned = re.sub(r"(?m)^\s*#{1,6}\s*", "", cleaned)

    # 9. Remove horizontal rules: ---, ***, ___
    cleaned = re.sub(r"(?m)^\s*[-*_]{3,}\s*$", "", cleaned)

    # 10. Remove bullet points at line starts (- item, * item, + item)
    cleaned = re.sub(r"(?m)^\s*[-*+]\s+", "", cleaned)

    # 11. Remove numbered lists at line starts (1. item, 2) item)
    cleaned = re.sub(r"(?m)^\s*\d+[\.\)]\s+", "", cleaned)

    # 12. Remove blockquotes (> item)
    cleaned = re.sub(r"(?m)^\s*>\s*", "", cleaned)

    # 13. Remove markdown table delimiter lines (|---|---|)
    cleaned = re.sub(r"(?m)^\s*\|?[-:\s|]+\|?\s*$", "", cleaned)
    # Remove leading and trailing pipes in table lines
    cleaned = re.sub(r"(?m)^\s*\|\s*", "", cleaned)
    cleaned = re.sub(r"(?m)\s*\|\s*$", "", cleaned)
    # Replace remaining pipes with commas
    cleaned = cleaned.replace("|", ", ")

    # 14. Strip any residual markdown markers
    cleaned = cleaned.replace("**", "").replace("*", "").replace("`", "").replace("#", "")

    # 15. Normalize whitespace and newlines
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    cleaned = " ".join(lines)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned