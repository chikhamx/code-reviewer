import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone

import httpx
from jinja2 import BaseLoader, Environment as JinjaEnv

from code_review_agent.models.review import ReviewResult
from code_review_agent.models.webhook import WebhookConfig, WebhookType

logger = logging.getLogger(__name__)


class WebhookDispatcher:
    """Dispatches review results to configured webhook endpoints with templates."""

    def __init__(self, webhooks: list[WebhookConfig]):
        self.webhooks = webhooks
        self._jinja = JinjaEnv(loader=BaseLoader())
        self._template_cache: dict[str, any] = {}

    async def dispatch(self, result: ReviewResult) -> dict[str, bool]:
        results: dict[str, bool] = {}
        async with httpx.AsyncClient(timeout=30) as client:
            for cfg in self.webhooks:
                if not cfg.enabled:
                    continue
                if not self._should_trigger(cfg, result):
                    continue
                try:
                    ok = await self._send(client, cfg, result)
                    results[cfg.name] = ok
                except Exception as e:
                    logger.error("Webhook '%s' failed: %s", cfg.name, e)
                    results[cfg.name] = False
        return results

    def _should_trigger(self, cfg: WebhookConfig, result: ReviewResult) -> bool:
        triggers = cfg.triggers

        # Check completion event
        if not triggers.on_review_complete:
            return False

        # Check severity threshold
        sev_order = {"critical": 5, "error": 4, "warning": 3, "info": 2, "suggestion": 1}
        min_sev = sev_order.get(triggers.min_severity, 3)
        for finding in result.findings:
            if sev_order.get(finding.severity.value, 0) >= min_sev:
                break
        else:
            if result.findings:
                return False

        # Check category filter
        if triggers.on_category:
            matched = any(f.category.value in triggers.on_category for f in result.findings)
            if not matched:
                return False

        return True

    async def _send(
        self, client: httpx.AsyncClient, cfg: WebhookConfig, result: ReviewResult,
    ) -> bool:
        payload = self._render_payload(cfg, result)
        headers = dict(cfg.headers)

        # HMAC signing
        if cfg.secret and cfg.type != WebhookType.generic:
            headers.update(self._sign(cfg, payload))

        headers.setdefault("Content-Type", "application/json")

        resp = await client.request(
            method=cfg.method,
            url=cfg.url,
            headers=headers,
            content=payload if isinstance(payload, str) else json.dumps(payload),
        )
        if resp.status_code >= 400:
            logger.warning(
                "Webhook '%s' returned %d: %s", cfg.name, resp.status_code, resp.text,
            )
            return False
        return True

    def _render_payload(self, cfg: WebhookConfig, result: ReviewResult) -> str:
        if cfg.type == WebhookType.feishu:
            return self._render_feishu_card(result)
        elif cfg.type == WebhookType.dingtalk:
            return self._render_dingtalk_md(result)
        elif cfg.type == WebhookType.wecom:
            return self._render_wecom_md(result)
        elif cfg.type == WebhookType.slack:
            return self._render_slack_block(result)
        else:
            return self._render_generic(cfg, result)

    def _render_generic(self, cfg: WebhookConfig, result: ReviewResult) -> str:
        template = cfg.body_template or cfg.template or "{}"
        ctx = self._make_context(result)
        tmpl = self._jinja.from_string(template)
        return tmpl.render(**ctx)

    def _make_context(self, result: ReviewResult) -> dict:
        return {
            "pr_title": result.pr_title,
            "pr_url": result.pr_url,
            "pr_number": result.pr_number,
            "branch": result.branch,
            "base_branch": result.base_branch,
            "repo_name": result.repo_name,
            "author": result.author,
            "risk_level": result.risk_level,
            "summary": result.summary,
            "findings": [f.model_dump() for f in result.findings],
            "findings_json": json.dumps([f.model_dump() for f in result.findings], ensure_ascii=False),
            "stats": result.stats.model_dump(),
            "stats_json": json.dumps(result.stats.model_dump()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "review_duration_ms": result.review_duration_ms,
        }

    def _sign(self, cfg: WebhookConfig, payload: str) -> dict:
        timestamp = str(int(time.time()))
        if cfg.type == WebhookType.feishu:
            sign_str = f"{timestamp}\n{cfg.secret}"
            signature = hmac.new(
                (cfg.secret or "").encode(), sign_str.encode(), hashlib.sha256,
            ).hexdigest()
            return {"X-Sign": signature, "X-Timestamp": timestamp}
        return {}

    # ── IM platform templates ──

    def _render_feishu_card(self, result: ReviewResult) -> str:
        risk_color = {"critical": "red", "high": "orange", "medium": "yellow", "low": "green"}
        findings_md = []
        for f in result.findings[:10]:
            icon = {"critical": "🔴", "error": "🟠", "warning": "🟡", "info": "🔵", "suggestion": "💡"}
            findings_md.append(
                f"- {icon.get(f.severity.value, '')} **{f.file}**"
                f"{':' + str(f.line) if f.line else ''}: {f.message[:100]}"
            )
        if len(result.findings) > 10:
            findings_md.append(f"... and {len(result.findings) - 10} more")

        card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"🤖 Code Review: {result.pr_title}"},
                    "template": risk_color.get(result.risk_level, "green"),
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": f"**Repo**: {result.repo_name}\n**Branch**: {result.branch} → {result.base_branch}\n**Author**: {result.author}\n**Risk**: {result.risk_level.upper()}",
                    },
                    {"tag": "hr"},
                    {"tag": "markdown", "content": "\n".join(findings_md) if findings_md else "No issues found ✅"},
                    {"tag": "hr"},
                    {
                        "tag": "markdown",
                        "content": f"📄 [View PR]({result.pr_url}) | ⏱️ {result.review_duration_ms}ms",
                    },
                ],
            },
        }
        return json.dumps(card, ensure_ascii=False)

    def _render_dingtalk_md(self, result: ReviewResult) -> str:
        lines = [
            f"## 🤖 Code Review: {result.pr_title}",
            f"",
            f"- **风险等级**: {result.risk_level.upper()}",
            f"- **分支**: {result.branch} → {result.base_branch}",
            f"- **作者**: {result.author}",
            f"- **发现问题**: {result.stats.total} 个",
            f"",
        ]
        for f in result.findings[:10]:
            lines.append(f"- [{f.severity.value.upper()}] `{f.file}:{f.line}` — {f.message[:80]}")
        return json.dumps({"msgtype": "markdown", "markdown": {"title": "Code Review", "text": "\n".join(lines)}})

    def _render_wecom_md(self, result: ReviewResult) -> str:
        lines = [
            f"## 🤖 Code Review: {result.pr_title}",
            f"> 风险等级: **{result.risk_level.upper()}**",
            f"> 分支: {result.branch} → {result.base_branch}",
        ]
        for f in result.findings[:10]:
            lines.append(f"- [{f.severity.value}] `{f.file}:{f.line}` — {f.message[:80]}")
        return json.dumps({"msgtype": "markdown", "markdown": {"content": "\n".join(lines)}})

    def _render_slack_block(self, result: ReviewResult) -> str:
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"🤖 Code Review: {result.pr_title}"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Risk:* {result.risk_level.upper()}"},
                    {"type": "mrkdwn", "text": f"*Branch:* {result.branch}"},
                    {"type": "mrkdwn", "text": f"*Author:* {result.author}"},
                    {"type": "mrkdwn", "text": f"*Findings:* {result.stats.total}"},
                ],
            },
        ]
        for f in result.findings[:10]:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"• `{f.file}:{f.line}` — {f.message[:100]}"},
            })
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"<{result.pr_url}|View PR>"}],
        })
        return json.dumps({"blocks": blocks})
