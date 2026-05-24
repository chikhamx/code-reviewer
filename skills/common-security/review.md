# Universal Security Review Guidelines

These rules apply to ALL code changes, regardless of language.

## Critical Checks
1. No credentials, tokens, or secrets in source code
2. All external API calls must use HTTPS
3. Authentication/authorization must be explicit
4. Input validation required for all user-controlled data
5. Sensitive data must not appear in logs or error messages
