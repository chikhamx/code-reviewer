"""Entry point for the Code Review Agent."""

import logging
import sys
from pathlib import Path

import uvicorn

logger = logging.getLogger(__name__)


def setup_logging(config):
    level = config.get("logging", "level", default="INFO")
    fmt = config.get("logging", "format", default="json")

    if fmt == "json":
        logging.basicConfig(
            level=getattr(logging, level.upper(), logging.INFO),
            format='{"time": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", "message": "%(message)s"}',
            stream=sys.stdout,
        )
    else:
        logging.basicConfig(
            level=getattr(logging, level.upper(), logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            stream=sys.stdout,
        )


def cmd_skill_new(args: list[str]):
    """Scaffold a new skill.

    Usage:
      cr-agent skill new <name> --type global
      cr-agent skill new <name> --type language --languages py,go
      cr-agent skill new <name> --type project
    """
    if len(args) < 1:
        print("Usage: cr-agent skill new <name> [--type global|language|project] [--languages py,go]")
        sys.exit(1)

    name = args[0]
    skill_type = "language"
    languages: list[str] = ["python"]
    for i, a in enumerate(args):
        if a == "--type" and i + 1 < len(args):
            skill_type = args[i + 1]
        if a == "--languages" and i + 1 < len(args):
            languages = [l.strip() for l in args[i + 1].split(",")]

    if skill_type not in ("global", "language", "project"):
        print(f"Invalid type: {skill_type}. Must be global, language, or project.")
        sys.exit(1)

    skill_dir = Path("skills") / name
    if skill_dir.exists():
        print(f"Skill '{name}' already exists at {skill_dir}")
        sys.exit(1)

    skill_dir.mkdir(parents=True)

    lang_list = ", ".join(languages) if skill_type == "language" else ""
    lang_line = f"languages: [{lang_list}]\n" if skill_type == "language" else ""

    (skill_dir / "skill.yaml").write_text(
        f"name: {name}\n"
        f"description: Custom review rules for {name}\n"
        f"version: \"1.0\"\n"
        f"type: {skill_type}\n"
        f"enabled: true\n"
        f"{lang_line}"
        f"author: Your Name\n",
        encoding="utf-8",
    )

    (skill_dir / "rules.yaml").write_text(
        "# Custom review rules (regex pattern matching)\n"
        "# Each rule: id, pattern, severity, category, message, suggestion\n"
        "rules:\n"
        "  # - id: my-rule-001\n"
        "  #   pattern: \"bad_pattern\"\n"
        "  #   severity: warning\n"
        "  #   category: maintainability\n"
        "  #   message: \"Short description of the issue\"\n"
        "  #   suggestion: \"How to fix it\"\n"
        "  #   files: \"*.py\"\n",
        encoding="utf-8",
    )

    (skill_dir / "review.md").write_text(
        f"# {name} Review Guidelines\n\n"
        "## Focus Areas\n"
        "- \n\n"
        "## Review Checklist\n"
        "1. \n\n"
        "## Style Notes\n"
        "- \n",
        encoding="utf-8",
    )

    print(f"Skill scaffolded: {skill_dir}/")
    print(f"  skill.yaml   — edit metadata")
    print(f"  rules.yaml   — add regex rules")
    print(f"  review.md    — write LLM review guidelines (CLAUDE.md / .cursorrules style)")


def cmd_skill_list():
    """List all installed skills."""
    skill_dir = Path("skills")
    if not skill_dir.exists():
        print("No skills directory found.")
        return

    from code_review_agent.skills.loader import SkillLoader
    loader = SkillLoader("skills")
    loader.load_global()  # trigger lazy load

    all_skills = loader.global_skills + loader.language_skills
    if not all_skills:
        print("No skills loaded.")
        return

    for s in all_skills:
        status = "✓" if s.enabled else "✗"
        rules_n = len(s.rules)
        prompt = "md" if s.review_prompt else "-"
        langs = ", ".join(s.languages) if s.languages else "all"
        print(f"  {status} {s.name:30s} [{s.skill_type.value:8s}] {rules_n:2d} rules  review={prompt}  langs={langs}")


def main():
    from code_review_agent.config import get_config

    # Check for subcommands
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "skill":
            sub = sys.argv[2] if len(sys.argv) > 2 else ""
            if sub == "new":
                cmd_skill_new(sys.argv[3:])
                return
            elif sub == "list" or sub == "ls":
                cmd_skill_list()
                return
            else:
                print("Usage: cr-agent skill <new|list>")
                print("  cr-agent skill new <name> [--languages py,go]")
                print("  cr-agent skill list")
                return
        elif cmd in ("--help", "-h", "help"):
            print("Code Review Agent")
            print()
            print("Usage:")
            print("  cr-agent                  Start the server")
            print("  cr-agent skill new <name> Scaffold a new skill")
            print("  cr-agent skill list       List installed skills")
            return

    config = get_config()
    setup_logging(config)

    host = config.get("server", "host", default="127.0.0.1")
    port = config.get("server", "port", default=8000)
    workers = config.get("server", "workers", default=1)

    logger.info("Starting Code Review Agent on %s:%d", host, port)

    uvicorn.run(
        "code_review_agent.api.app:app",
        host=host,
        port=port,
        workers=workers,
        log_level="info",
    )


if __name__ == "__main__":
    main()
