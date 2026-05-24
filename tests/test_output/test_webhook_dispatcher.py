import pytest

from code_review_agent.models.review import Finding, FindingCategory, FindingSeverity, ReviewResult
from code_review_agent.models.webhook import TriggerConfig, WebhookConfig, WebhookType


def make_result(findings_count=2):
    result = ReviewResult(
        pr_title="Test PR",
        pr_url="https://github.com/test/repo/pull/1",
        pr_number=1,
        branch="feature/x",
        base_branch="main",
        repo_name="test/repo",
        author="testuser",
    )
    result.findings = [
        Finding(
            file="a.py", line=10,
            severity=FindingSeverity.error,
            category=FindingCategory.security,
            title="Issue 1", message="Security problem",
        ),
        Finding(
            file="b.py", line=20,
            severity=FindingSeverity.warning,
            category=FindingCategory.maintainability,
            title="Issue 2", message="Style problem",
        ),
    ][:findings_count]
    result.compute_stats()
    return result


class TestShouldTrigger:
    def test_triggers_on_complete(self):
        cfg = WebhookConfig(
            name="test",
            type=WebhookType.generic,
            url="https://example.com",
            triggers=TriggerConfig(on_review_complete=True),
        )
        from code_review_agent.output.webhook_dispatcher import WebhookDispatcher
        dispatcher = WebhookDispatcher([cfg])
        assert dispatcher._should_trigger(cfg, make_result())

    def test_no_trigger_if_disabled(self):
        cfg = WebhookConfig(
            name="test",
            enabled=False,
            type=WebhookType.generic,
            url="https://example.com",
            triggers=TriggerConfig(on_review_complete=True),
        )
        from code_review_agent.output.webhook_dispatcher import WebhookDispatcher
        dispatcher = WebhookDispatcher([cfg])
        assert not dispatcher._should_trigger(cfg, make_result())

    def test_min_severity_filter(self):
        cfg = WebhookConfig(
            name="test",
            type=WebhookType.generic,
            url="https://example.com",
            triggers=TriggerConfig(min_severity="critical", on_review_complete=True),
        )
        from code_review_agent.output.webhook_dispatcher import WebhookDispatcher
        dispatcher = WebhookDispatcher([cfg])
        # No critical findings → should not trigger
        assert not dispatcher._should_trigger(cfg, make_result())

    def test_category_filter(self):
        cfg = WebhookConfig(
            name="test",
            type=WebhookType.generic,
            url="https://example.com",
            triggers=TriggerConfig(on_category=["performance"], on_review_complete=True),
        )
        from code_review_agent.output.webhook_dispatcher import WebhookDispatcher
        dispatcher = WebhookDispatcher([cfg])
        assert not dispatcher._should_trigger(cfg, make_result())  # no performance findings
