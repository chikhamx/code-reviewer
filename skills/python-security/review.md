# Python Security Review Guidelines

## Focus Areas
- SQL injection via string formatting (f-strings, %-formatting)
- Command injection via os.system, subprocess with shell=True
- Unsafe deserialization (pickle, yaml.load)
- Hardcoded secrets and API keys
- Insecure cryptography (MD5, SHA1 for passwords, weak random)
- Path traversal vulnerabilities

## Review Checklist
1. All database queries must use parameterized queries
2. No eval() or exec() on user-controlled input
3. Secrets must come from environment variables or secret manager
4. File operations must validate paths (no path traversal)
5. HTTPS must be enforced for external API calls
6. Authentication/authorization logic must be explicit, not implicit

## Style Notes
- Prefer dataclasses over raw dicts for structured data
- Use type hints consistently
- Handle exceptions explicitly, avoid bare `except:`
