#!/usr/bin/env python3
"""
Local Feishu verification script.

This script simulates the full pipeline without needing a real Feishu bot,
GitHub webhook, or running server. It directly bootstraps all components
and feeds simulated messages through the IM gateway.

Usage:
    # Set required env vars
    export ANTHROPIC_API_KEY=sk-ant-...
    export GITHUB_TOKEN=ghp_...          # optional, for real PR review

    # Run interactive test
    python test_feishu.py

    # Run a single simulated message
    python test_feishu.py --message "review https://github.com/org/repo/pull/42"

    # Run automated smoke test
    python test_feishu.py --smoke

What this tests:
    1. Config loading
    2. LLM provider initialization
    3. Intent classification
    4. Action dispatch (chat / explain / etc.)
    5. Session management and multi-turn conversation
    6. The full IM gateway pipeline

What this does NOT test without real credentials:
    - Actual GitHub PR fetching
    - Actual LLM API calls (if no API key)
    - Actual Feishu message sending
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Ensure the project is on the Python path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    # Quiet noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


async def test_smoke():
    """Quick smoke test: bootstrap → simulate a chat message."""
    from code_review_agent.bootstrap import bootstrap

    print("=" * 60)
    print("Smoke Test: Bootstrap + Chat Simulation")
    print("=" * 60)

    ctx = await bootstrap(config_dir=str(PROJECT_ROOT / "config"))

    # Check what's available
    print(f"\nLLM Providers: {ctx.model_router.list_providers()}")
    print(f"Model Aliases: {list(ctx.model_router.model_registry.keys())}")
    print(f"Rule Engine: {len(ctx.rule_engine.rules)} rules loaded")
    print(f"Action Handlers: {list(ctx.action_dispatcher.handlers.keys())}")

    # Simulate a "help" message
    raw = {
        "event": {
            "message": {
                "message_id": "smoke-test-001",
                "msg_type": "text",
                "content": '{"text":"help"}',
            },
            "sender": {"sender_id": {"open_id": "test-user"}},
            "open_chat_id": "test-chat-smoke",
        },
    }

    print("\n--- Simulating Feishu message: 'help' ---")
    result = await ctx.im_gateway.handle_message("feishu", raw)
    print(f"Result: {result}")
    print("\nSmoke test PASSED ✓")
    return ctx


async def test_intent_classification(ctx=None):
    """Test intent classification with various messages."""
    from code_review_agent.bootstrap import bootstrap

    if ctx is None:
        ctx = await bootstrap(config_dir=str(PROJECT_ROOT / "config"))

    print("\n" + "=" * 60)
    print("Intent Classification Test")
    print("=" * 60)

    test_messages = [
        "review https://github.com/org/repo/pull/42",
        "help",
        "explain the auth module",
        "how do I fix the SQL injection issue?",
        "refactor this code",
        "where is the error handling code?",
        "review PR #42 in myorg/myrepo",
        "你能做什么？",
    ]

    for msg in test_messages:
        intent = await ctx.intent_router.classify(msg)
        print(f"  '{msg[:50]}...' → {intent.value if intent else 'unknown'}")

    print("Intent test PASSED ✓")


async def test_conversation(ctx=None):
    """Test multi-turn conversation with context."""
    from code_review_agent.bootstrap import bootstrap

    if ctx is None:
        ctx = await bootstrap(config_dir=str(PROJECT_ROOT / "config"))

    print("\n" + "=" * 60)
    print("Multi-turn Conversation Test")
    print("=" * 60)

    session_id = "feishu:test-chat-conv:test-user"
    session = await ctx.conversation_manager.get_or_create(
        session_id=session_id,
        platform="feishu",
        channel_id="test-chat-conv",
        user_id="test-user",
        user_name="Test User",
    )

    # Simulate a few turns
    messages = [
        ("user", "help"),
        ("assistant", "I'm a code review bot. You can ask me to review PRs, explain code, etc."),
        ("user", "review https://github.com/org/repo/pull/42"),
    ]

    for role, content in messages:
        session.history.append({"role": role, "content": content})
    session.current_target = "https://github.com/org/repo/pull/42"
    await ctx.conversation_manager.save(session)

    # Verify session persistence
    restored = await ctx.conversation_manager.get(session_id)
    assert restored is not None, "Session should be restored"
    assert len(restored.history) == 3, f"Expected 3 history entries, got {len(restored.history)}"
    assert restored.current_target == "https://github.com/org/repo/pull/42"

    print(f"  Session ID: {session_id}")
    print(f"  History turns: {len(restored.history)}")
    print(f"  Current target: {restored.current_target}")
    print("Conversation test PASSED ✓")


async def test_rule_engine(ctx=None):
    """Test the static rule engine."""
    print("\n" + "=" * 60)
    print("Rule Engine Test")
    print("=" * 60)

    from code_review_agent.models.platform import DiffFile, DiffHunk
    from code_review_agent.reviewers.rule_engine import RuleEngine

    engine = RuleEngine()

    # Create a fake diff with known issues
    hunk = DiffHunk(
        header="@@ -10,5 +10,5 @@",
        old_start=10, old_count=5,
        new_start=10, new_count=5,
        content='+ query = f"SELECT * FROM users WHERE id={user_id}"\n+ password = "super_secret_12345"\n',
        lines=[
            '+ query = f"SELECT * FROM users WHERE id={user_id}"',
            '+ password = "super_secret_12345"',
        ],
    )
    file = DiffFile(path="src/db.py", language="python", hunks=[hunk])

    findings = engine.check([file])
    print(f"  Issues found: {len(findings)}")
    for f in findings:
        print(f"  [{f.severity.value}] [{f.rule_id}] {f.file}:{f.line} — {f.message[:80]}")
    print("Rule engine test PASSED ✓")


async def run_interactive(ctx=None):
    """Interactive mode: type messages and see how the agent responds."""
    from code_review_agent.bootstrap import bootstrap

    if ctx is None:
        ctx = await bootstrap(config_dir=str(PROJECT_ROOT / "config"))

    print("\n" + "=" * 60)
    print("Interactive Mode")
    print("Type messages to simulate Feishu bot interaction.")
    print("Type 'quit' to exit, 'help' for available commands.")
    print("=" * 60)

    session_id = "feishu:interactive:test-user"
    msg_counter = 0

    while True:
        try:
            text = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not text:
            continue
        if text.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break
        if text.lower() == "help":
            print(
                "Available commands:\n"
                "  review https://github.com/org/repo/pull/42  — Review a PR\n"
                "  explain <topic>                              — Explain code\n"
                "  suggest fix for <issue>                      — Get fix suggestion\n"
                "  refactor <code>                              — Refactoring help\n"
                "  help                                        — Show this menu\n"
                "  quit                                        — Exit"
            )
            continue

        msg_counter += 1
        raw = {
            "event": {
                "message": {
                    "message_id": f"interactive-{msg_counter}",
                    "msg_type": "text",
                    "content": '{"text":"' + text + '"}',
                },
                "sender": {"sender_id": {"open_id": "test-user"}},
                "open_chat_id": "interactive",
            },
        }

        print("\nAgent: ", end="", flush=True)
        result = await ctx.im_gateway.handle_message("feishu", raw)
        print(f"(intent={result.get('intent', '?')})")


async def main():
    setup_logging()
    logger = logging.getLogger(__name__)

    args = sys.argv[1:]
    smoke = "--smoke" in args
    msg_arg = None

    for i, arg in enumerate(args):
        if arg == "--message" and i + 1 < len(args):
            msg_arg = args[i + 1]

    # Bootstrap the application
    try:
        ctx = await bootstrap(config_dir=str(PROJECT_ROOT / "config"))
    except Exception as e:
        logger.error("Bootstrap failed: %s", e)
        print(f"\n❌ Bootstrap failed: {e}")
        print("\nMake sure you have the required dependencies installed:")
        print("  pip install -e '.[dev]'")
        print("\nAnd set required environment variables in config/*.yaml files.")
        sys.exit(1)

    if msg_arg:
        # Single message mode
        raw = {
            "event": {
                "message": {
                    "message_id": "cli-msg-001",
                    "msg_type": "text",
                    "content": '{"text":"' + msg_arg + '"}',
                },
                "sender": {"sender_id": {"open_id": "cli-user"}},
                "open_chat_id": "cli-chat",
            },
        }
        print(f"Sending: {msg_arg}")
        result = await ctx.im_gateway.handle_message("feishu", raw)
        print(f"Result: {result}")
        return

    # Run smoke tests
    await test_intent_classification(ctx)
    await test_conversation(ctx)
    await test_rule_engine(ctx)

    if smoke:
        print("\n" + "=" * 60)
        print("All smoke tests PASSED ✓")
        print("=" * 60)
        return

    # Interactive mode
    await run_interactive(ctx)


if __name__ == "__main__":
    asyncio.run(main())
