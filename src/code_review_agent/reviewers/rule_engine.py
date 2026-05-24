import re
import logging

from code_review_agent.models.platform import DiffFile
from code_review_agent.models.review import Finding, FindingCategory, FindingSeverity

logger = logging.getLogger(__name__)


class RuleEngine:
    """Static rule engine for pattern-based code checks."""

    def __init__(self, rules: list[dict] | None = None):
        self.rules: list[dict] = rules or self._default_rules()

    def check(self, files: list[DiffFile]) -> list[Finding]:
        findings: list[Finding] = []
        for rule in self.rules:
            if not rule.get("enabled", True):
                continue
            try:
                results = self._apply_rule(rule, files)
                findings.extend(results)
            except Exception as e:
                logger.warning("Rule '%s' failed: %s", rule.get("id", "unknown"), e)
        return findings

    def _apply_rule(self, rule: dict, files: list[DiffFile]) -> list[Finding]:
        findings: list[Finding] = []
        pattern = re.compile(rule["pattern"])

        # Filter files by language/glob
        file_filter = rule.get("files", "*")
        applicable = self._filter_files(files, file_filter)

        for df in applicable:
            for hunk in df.hunks:
                for idx, line_text in enumerate(hunk.lines):
                    if not line_text.startswith("+"):
                        continue
                    code = line_text[1:]  # strip the + prefix
                    match = pattern.search(code)
                    if match:
                        # Skip lines that are comments or test files if configured
                        if rule.get("skip_comments") and code.strip().startswith(("//", "#", "--")):
                            continue
                        if rule.get("skip_tests") and self._is_test_file(df.path):
                            continue

                        line_number = hunk.new_start + idx - 1  # approximate
                        findings.append(Finding(
                            file=df.path,
                            line=line_number,
                            severity=self._parse_severity(rule.get("severity", "warning")),
                            category=self._parse_category(rule.get("category", "maintainability")),
                            title=rule.get("message", "Rule violation"),
                            message=rule.get("description", rule.get("message", "")),
                            suggestion=rule.get("suggestion"),
                            rule_id=rule.get("id"),
                            code_snippet=code.strip()[:200],
                        ))
        return findings

    def add_rule(self, rule: dict) -> None:
        self.rules.append(rule)

    def remove_rule(self, rule_id: str) -> None:
        self.rules = [r for r in self.rules if r.get("id") != rule_id]

    @staticmethod
    def _filter_files(files: list[DiffFile], pattern: str) -> list[DiffFile]:
        if pattern == "*":
            return files
        patterns = [p.strip() for p in pattern.split(",")]
        result = []
        for df in files:
            for pat in patterns:
                if _simple_glob_match(pat, df.path):
                    result.append(df)
                    break
        return result

    @staticmethod
    def _is_test_file(path: str) -> bool:
        return "test" in path.lower() or path.lower().startswith("test")

    @staticmethod
    def _parse_severity(raw: str) -> FindingSeverity:
        try:
            return FindingSeverity(raw)
        except ValueError:
            return FindingSeverity.warning

    @staticmethod
    def _parse_category(raw: str) -> FindingCategory:
        try:
            return FindingCategory(raw)
        except ValueError:
            return FindingCategory.maintainability

    @staticmethod
    def _default_rules() -> list[dict]:
        return [
            {
                "id": "R001",
                "message": "Potential SQL injection: string formatting in SQL query",
                "pattern": r"(execute|cursor\.execute|raw_query)\s*\(\s*f['\"]",
                "category": "security",
                "severity": "error",
                "files": "*.py",
                "enabled": True,
                "suggestion": "Use parameterized queries instead of string formatting.",
            },
            {
                "id": "R002",
                "message": "Hardcoded secret or credential detected",
                "pattern": r"(password|secret|api_key|token)\s*=\s*['\"][^'\"]{8,}['\"]",
                "category": "security",
                "severity": "critical",
                "files": "*.py,*.js,*.ts,*.go,*.java,*.yaml,*.yml",
                "enabled": True,
                "suggestion": "Use environment variables or a secret manager.",
            },
            {
                "id": "R003",
                "message": "Debug print or console.log left in code",
                "pattern": r"\b(print|console\.log|console\.debug|fmt\.Println|System\.out\.println)\s*\(",
                "category": "maintainability",
                "severity": "info",
                "files": "*",
                "enabled": True,
                "suggestion": "Remove debug output or use proper logging.",
            },
            {
                "id": "R004",
                "message": "Bare except clause (catches too broadly)",
                "pattern": r"except\s*:",
                "category": "bug_risk",
                "severity": "warning",
                "files": "*.py",
                "enabled": True,
                "suggestion": "Specify the exception type(s) to catch.",
            },
            {
                "id": "R005",
                "message": "TODO/FIXME/HACK comment without tracking reference",
                "pattern": r"\b(TODO|FIXME|HACK)\b(?!\s*[\(\[]?\s*#?\d+)",
                "category": "maintainability",
                "severity": "info",
                "files": "*",
                "enabled": True,
                "suggestion": "Add issue/PR reference to the TODO comment.",
            },
        ]


def _simple_glob_match(pattern: str, path: str) -> bool:
    """Simple glob match: '*.py' matches 'foo/bar/baz.py'."""
    if pattern.startswith("*."):
        return path.endswith(pattern[1:])
    if pattern == "*":
        return True
    return path == pattern
