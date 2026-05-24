# JavaScript/TypeScript Code Review Guidelines

## Focus Areas
- XSS prevention: never use innerHTML, document.write with user input
- No eval() / new Function() with dynamic content
- CSRF protection on state-changing requests
- Secrets and tokens must not appear in client-side code
- Avoid prototype pollution

## Review Checklist
1. User input must be sanitized before rendering (use textContent, DOMPurify)
2. Never use eval(), new Function(), or setTimeout with string arguments
3. API calls must validate responses and handle errors
4. Sensitive data must not be logged to console
5. Use strict mode ('use strict') in all modules
6. Avoid synchronous XMLHttpRequest and blocking operations

## Style Notes
- Prefer const over let; never use var
- Use async/await over raw Promise chains
- Use template literals over string concatenation
- Prefer === over ==
