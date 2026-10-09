from __future__ import annotations

from ...application.skills.question_tagger import build_tagging_prompt
from ...application.skills.taxonomy import SkillTaxonomy, get_default_taxonomy


def suggest_skill_ids_with_llm(
    question_text: str,
    *,
    taxonomy: SkillTaxonomy | None = None,
    base_url: str,
    api_key: str,
    model: str,
    timeout: float = 30.0,
) -> list[str]:
    """Gợi ý nhãn kỹ năng bằng LLM, chỉ giữ id hợp lệ trong taxonomy.

    Kết quả chỉ để người dùng rà lại; hàm này không ghi DB.
    """
    taxonomy = taxonomy or get_default_taxonomy()
    import httpx

    resp = httpx.post(
        base_url.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": build_tagging_prompt(question_text, taxonomy)}],
            "temperature": 0,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = resp.json()
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return []

    valid: list[str] = []
    for raw_id in extract_json_ids(content):
        sid = taxonomy.normalize_skill_id(raw_id)
        if sid and sid not in valid:
            valid.append(sid)
    return valid


def extract_json_ids(content: str) -> list[str]:
    import json
    import re

    if not content:
        return []
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except Exception:
        return []
    raw = data.get("skill_ids")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str)]
