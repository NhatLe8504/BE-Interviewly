from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any


# Alias quá ngắn/generic vẫn được chấp nhận khi người dùng gứi đúng từ khóa
# (normalize_skill) nhưng KHÔNG được quét trong văn bản tự do, vì sẽ khớp nhầm
# (ví dụ "go" trong "go to our careers page" bị gán thành Go, hoặc "js"
# trong "Next.js" bị gán thành JavaScript).
SCAN_EXCLUDED_ALIASES = frozenset({"go", "js"})


@dataclass(frozen=True)
class SkillDefinition:
    id: str
    name: str
    category: str
    role_tracks: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)


class SkillTaxonomy:
    def __init__(self, data_path: Path | None = None) -> None:
        if data_path is None:
            data_path = Path(__file__).parent / "skill_taxonomy.json"
        self._skills: dict[str, SkillDefinition] = {}
        self._alias_map: dict[str, str] = {}
        self._load(data_path)

    def _load(self, path: Path) -> None:
        if not path.exists():
            return
        raw_items = json.loads(path.read_text(encoding="utf-8"))
        for item in raw_items:
            skill = SkillDefinition(
                id=item["id"],
                name=item["name"],
                category=item["category"],
                role_tracks=item.get("role_tracks", []),
                aliases=[a.strip().lower() for a in item.get("aliases", []) if a.strip()],
            )
            self._skills[skill.id] = skill
            self._alias_map[skill.id.lower()] = skill.id
            self._alias_map[skill.name.lower()] = skill.id
            for alias in skill.aliases:
                self._alias_map[alias] = skill.id

    def get_skill(self, skill_id: str) -> SkillDefinition | None:
        return self._skills.get(skill_id.lower())

    def normalize_skill(self, raw: str) -> SkillDefinition | None:
        if not raw or not isinstance(raw, str):
            return None
        cleaned = re.sub(r"[\t\r\n]+", " ", raw).strip().lower()
        cleaned = re.sub(r"\s+", " ", cleaned)
        if not cleaned:
            return None
        # Direct lookup
        if cleaned in self._alias_map:
            return self._skills.get(self._alias_map[cleaned])
        # Punctuation stripped check
        stripped = re.sub(r"[^\w\s\+\#\.]", "", cleaned).strip()
        if stripped in self._alias_map:
            return self._skills.get(self._alias_map[stripped])
        return None

    def normalize_skill_id(self, raw: str) -> str | None:
        skill = self.normalize_skill(raw)
        return skill.id if skill else None

    def extract_skills_from_text(self, text: str) -> list[SkillDefinition]:
        if not text:
            return []
        found: dict[str, SkillDefinition] = {}
        lower_text = text.lower()
        # Sort aliases by length descending to match multi-word phrases first (e.g. 'spring boot' before 'spring')
        sorted_aliases = sorted(self._alias_map.items(), key=lambda x: len(x[0]), reverse=True)
        for alias, skill_id in sorted_aliases:
            if skill_id in found or alias in SCAN_EXCLUDED_ALIASES:
                continue
            # Word boundary regex
            pattern = r"(?:\b|\A)" + re.escape(alias) + r"(?:\b|\Z)"
            if re.search(pattern, lower_text):
                found[skill_id] = self._skills[skill_id]
        return list(found.values())

    def get_skills_for_role(self, role_track: str) -> list[SkillDefinition]:
        norm = role_track.strip().lower()
        return [s for s in self._skills.values() if norm in s.role_tracks]

    def all_skills(self) -> list[SkillDefinition]:
        return list(self._skills.values())


_default_taxonomy: SkillTaxonomy | None = None


def get_default_taxonomy() -> SkillTaxonomy:
    global _default_taxonomy
    if _default_taxonomy is None:
        _default_taxonomy = SkillTaxonomy()
    return _default_taxonomy
