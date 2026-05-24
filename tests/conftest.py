import pytest


@pytest.fixture
def sample_diff():
    return """diff --git a/src/auth.py b/src/auth.py
index 1234567..abcdefg 100644
--- a/src/auth.py
+++ b/src/auth.py
@@ -10,7 +10,7 @@ def login(username, password):
     user = db.query(User).filter(User.username == username).first()
     if not user:
         return {"error": "User not found"}
-    if user.check_password(password):
+    if user.password == password:
         token = generate_token(user)
         return {"token": token}
     return {"error": "Invalid password"}
@@ -25,5 +25,6 @@ def generate_token(user):
         "user_id": user.id,
         "exp": datetime.utcnow() + timedelta(hours=24)
     }
-    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")
+    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
+    print(f"Generated token: {token}")
+    return token
"""


@pytest.fixture
def mock_llm_config():
    return {
        "providers": {
            "claude": {
                "enabled": False,
                "api_key": "test-key",
                "base_url": None,
                "models": [
                    {"id": "claude-sonnet-4-6", "alias": ["smart", "default"], "max_tokens": 8192},
                    {"id": "claude-haiku-4-5", "alias": ["fast"], "max_tokens": 4096},
                ],
            }
        },
        "pricing": {
            "claude": {"claude-sonnet-4-6": [3.0, 15.0], "claude-haiku-4-5": [0.8, 4.0]},
        },
        "task_model_map": {},
    }


@pytest.fixture
def mock_webhook_configs():
    from code_review_agent.models.webhook import WebhookConfig, WebhookType, TriggerConfig

    return [
        WebhookConfig(
            name="test-feishu",
            enabled=True,
            type=WebhookType.feishu,
            url="https://example.com/hook",
            triggers=TriggerConfig(on_review_complete=True),
        )
    ]


@pytest.fixture
def sample_findings():
    from code_review_agent.models.review import Finding, FindingCategory, FindingSeverity

    return [
        Finding(
            file="src/auth.py",
            line=13,
            severity=FindingSeverity.critical,
            category=FindingCategory.security,
            title="Plain-text password comparison",
            message="Password is compared in plain text instead of using check_password()",
            suggestion="Use user.check_password(password) to verify the password hash.",
        ),
        Finding(
            file="src/auth.py",
            line=15,
            severity=FindingSeverity.warning,
            category=FindingCategory.maintainability,
            title="Debug print statement",
            message="Print statement leaks sensitive token information.",
            suggestion="Remove the print statement or replace with proper logging.",
        ),
    ]
