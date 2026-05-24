# Error Handling Review Guidelines

## Focus Areas
- Exceptions must be specific and meaningful
- Never silently swallow errors without logging
- Error messages must contain actionable information
- Recovery strategies must be explicit

## Review Checklist
1. Every catch/except block must log or propagate the error
2. Exception types must be as specific as possible
3. Error messages must include context (what failed, why, what to do)
4. Resource cleanup must happen in finally/defer blocks
5. Retry logic must have exponential backoff and max attempts
