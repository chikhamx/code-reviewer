from code_review_agent.models.platform import DiffFile, DiffHunk
from code_review_agent.reviewers.rule_engine import RuleEngine


def test_rule_engine_detects_sql_injection():
    engine = RuleEngine()
    hunk = DiffHunk(
        header="@@ -10,5 +10,5 @@",
        old_start=10, old_count=5, new_start=10, new_count=5,
        content="+ query = f\"SELECT * FROM users WHERE id={user_id}\"\n",
        lines=["+ query = f\"SELECT * FROM users WHERE id={user_id}\""],
    )
    file = DiffFile(path="src/db.py", language="python", hunks=[hunk])

    findings = engine.check([file])
    assert len(findings) >= 1
    assert any("SQL" in f.title for f in findings)


def test_rule_engine_detects_hardcoded_secret():
    engine = RuleEngine()
    hunk = DiffHunk(
        header="@@ -1,0 +1,3 @@",
        old_start=1, old_count=0, new_start=1, new_count=3,
        content="+ password = \"super_secret_12345\"\n",
        lines=["+ password = \"super_secret_12345\""],
    )
    file = DiffFile(path="config.py", language="python", hunks=[hunk])

    findings = engine.check([file])
    assert any("secret" in f.title.lower() or "credential" in f.title.lower() for f in findings)


def test_rule_engine_detects_debug_print():
    engine = RuleEngine()
    hunk = DiffHunk(
        header="@@ -5,0 +5,1 @@",
        old_start=5, old_count=0, new_start=5, new_count=1,
        content="+ print(f\"debug: {token}\")\n",
        lines=["+ print(f\"debug: {token}\")"],
    )
    file = DiffFile(path="app.py", language="python", hunks=[hunk])

    findings = engine.check([file])
    assert any("print" in f.message.lower() for f in findings)


def test_rule_engine_respects_file_filter():
    engine = RuleEngine()
    hunk = DiffHunk(
        header="@@ -1,0 +1,1 @@",
        old_start=1, old_count=0, new_start=1, new_count=1,
        content="+ query = f\"SELECT * FROM users WHERE id={x}\"\n",
        lines=["+ query = f\"SELECT * FROM users WHERE id={x}\""],
    )
    # SQL injection rule only applies to *.py, not *.js
    file = DiffFile(path="app.js", language="javascript", hunks=[hunk])

    findings = engine.check([file])
    # R001 (SQL injection) should not fire for .js files
    sql_findings = [f for f in findings if f.rule_id == "R001"]
    assert len(sql_findings) == 0


def test_rule_engine_custom_rule():
    engine = RuleEngine(rules=[
        {
            "id": "CUSTOM001",
            "message": "Custom rule violation",
            "pattern": r"eval\s*\(",
            "category": "security",
            "severity": "critical",
            "files": "*",
            "enabled": True,
            "suggestion": "Avoid using eval().",
        }
    ])
    hunk = DiffHunk(
        header="@@ -1,0 +1,1 @@",
        old_start=1, old_count=0, new_start=1, new_count=1,
        content="+ eval(user_input)\n",
        lines=["+ eval(user_input)"],
    )
    file = DiffFile(path="app.py", language="python", hunks=[hunk])

    findings = engine.check([file])
    assert len(findings) == 1
    assert findings[0].rule_id == "CUSTOM001"
