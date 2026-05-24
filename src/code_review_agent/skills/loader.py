"""Skill loader with directory-based three-tier system.

Tiers are determined by the parent directory under skills/:

    skills/
      global/           ← Tier 1: always loaded, applies to ALL projects
        common-security/
          skill.yaml
          rules.yaml
          review.md
      language/         ← Tier 2: loaded per-review based on PR file languages
        python-security/
          skill.yaml
          rules.yaml
          review.md
        go-best-practices/
          skill.yaml
          rules.yaml
      project/          ← Tier 3: user-defined per-project skills
        my-project/
          skill.yaml
          rules.yaml
          review.md

Each skill directory:
    skill.yaml          # metadata (name, languages, enabled)
    rules.yaml          # structured regex rules (optional)
    review.md           # LLM review guidelines (optional, markdown)
"""

import logging
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


class Skill:
    """A loaded skill with metadata, rules, and optional review prompt."""

    def __init__(self, name: str, tier: str, path: Path, metadata: dict):
        self.name = name
        self.tier = tier  # "global" | "language" | "project"
        self.path = path
        self.metadata = metadata
        self.rules: list[dict] = []
        self.review_prompt: str = ""

    @property
    def enabled(self) -> bool:
        return self.metadata.get("enabled", True)

    @property
    def languages(self) -> list[str]:
        return self.metadata.get("languages", [])


class SkillLoader:
    """Loads skills from the skills/ directory using directory-based tiers."""

    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = Path(skills_dir)
        self.global_skills: list[Skill] = []
        self.language_skills: list[Skill] = []
        self.project_skills: list[Skill] = []
        self._loaded = False

    # ── Discovery ──

    def _discover_in(self, tier: str) -> list[Path]:
        tier_dir = self.skills_dir / tier
        if not tier_dir.exists():
            return []
        return sorted(
            d for d in tier_dir.iterdir()
            if d.is_dir() and (d / "skill.yaml").exists()
        )

    # ── Tier 1: Global ──

    def get_global_rules(self) -> list[dict]:
        self._ensure_loaded()
        rules: list[dict] = []
        for s in self.global_skills:
            rules.extend(s.rules)
        return rules

    def get_global_prompts(self) -> str:
        self._ensure_loaded()
        return _join_prompts(self.global_skills)

    # ── Tier 2: Language-specific (for review time) ──

    def get_rules_for_languages(self, languages: list[str]) -> list[dict]:
        """Get rules from global + matching language skills."""
        self._ensure_loaded()
        rules: list[dict] = []
        for s in self.global_skills:
            rules.extend(s.rules)
        for s in self.language_skills:
            if _language_match(s.languages, languages):
                rules.extend(s.rules)
        return rules

    def get_prompts_for_languages(self, languages: list[str]) -> str:
        """Get review.md from global + matching language skills."""
        self._ensure_loaded()
        prompts: list[str] = []
        for s in self.global_skills:
            if s.review_prompt:
                prompts.append(f"## {s.name}\n{s.review_prompt}")
        for s in self.language_skills:
            if s.review_prompt and _language_match(s.languages, languages):
                prompts.append(f"## {s.name}\n{s.review_prompt}")
        return "\n\n".join(prompts)

    # ── Tier 3: Project-level (.code-review/ in reviewed repo) ──

    @staticmethod
    def load_project_rules(rules_yaml_text: str) -> list[dict]:
        if not rules_yaml_text.strip():
            return []
        try:
            data = yaml.safe_load(rules_yaml_text) or {}
            return data.get("rules", [])
        except yaml.YAMLError as e:
            logger.warning("Failed to parse project rules.yaml: %s", e)
            return []

    @staticmethod
    def load_project_prompt(review_md_text: str) -> str:
        text = review_md_text.strip()
        if not text:
            return ""
        return "## Project Rules (.code-review/)\n" + text

    def get_all_skills(self) -> list[Skill]:
        self._ensure_loaded()
        return self.global_skills + self.language_skills + self.project_skills

    # ── Internal ──

    def _ensure_loaded(self):
        if self._loaded:
            return
        for tier in ("global", "language", "project"):
            for skill_dir in self._discover_in(tier):
                skill = self._load_skill(tier, skill_dir)
                if not skill or not skill.enabled:
                    if skill:
                        logger.info("Skill skipped (disabled): %s/%s", tier, skill.name)
                    continue

                target = (
                    self.global_skills if tier == "global"
                    else self.language_skills if tier == "language"
                    else self.project_skills
                )
                target.append(skill)

                parts = [f"{len(skill.rules)} rules"]
                if skill.review_prompt:
                    parts.append(f"review.md ({len(skill.review_prompt)} chars)")
                if skill.languages:
                    parts.append(f"langs={skill.languages}")
                logger.info(
                    "Skill loaded: [%s] %s (%s)",
                    tier, skill.name, ", ".join(parts),
                )
        self._loaded = True

    def _load_skill(self, tier: str, skill_dir: Path) -> Optional[Skill]:
        manifest = self._read_yaml(skill_dir / "skill.yaml")
        if not manifest:
            return None
        name = manifest.get("name", skill_dir.name)
        skill = Skill(name=name, tier=tier, path=skill_dir, metadata=manifest)
        rules_data = self._read_yaml(skill_dir / "rules.yaml")
        if rules_data:
            skill.rules = rules_data.get("rules", [])
            self._validate_rules(skill.rules, skill.name)
        skill.review_prompt = self._read_text(skill_dir / "review.md")
        return skill

    @staticmethod
    def _read_yaml(path: Path) -> Optional[dict]:
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error("Failed to parse %s: %s", path, e)
            return None

    @staticmethod
    def _read_text(path: Path) -> str:
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.error("Failed to read %s: %s", path, e)
            return ""

    @staticmethod
    def _validate_rules(rules: list[dict], skill_name: str) -> None:
        for rule in rules:
            if "id" not in rule:
                logger.warning("Rule missing 'id' in skill %s", skill_name)
            if "pattern" not in rule:
                logger.warning(
                    "Rule '%s' missing 'pattern' in skill %s",
                    rule.get("id", "?"), skill_name,
                )


def _language_match(skill_langs: list[str], target_langs: list[str]) -> bool:
    if not skill_langs:
        return True
    skill_set = set(s.lower() for s in skill_langs)
    target_set = set(t.lower() for t in target_langs)
    return bool(skill_set & target_set)


def _join_prompts(skills: list[Skill]) -> str:
    prompts: list[str] = []
    for s in skills:
        if s.review_prompt:
            prompts.append(f"## {s.name}\n{s.review_prompt}")
    return "\n\n".join(prompts)
