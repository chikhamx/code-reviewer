# Go Code Review Guidelines

## Focus Areas
- Error handling: every error must be checked or explicitly ignored
- Goroutine safety: check for data races, mutex usage, channel patterns
- Context propagation: all long-running operations should accept context.Context
- Resource management: files, connections, goroutines must be cleaned up

## Review Checklist
1. All errors returned from functions must be checked
2. No naked returns in functions longer than 10 lines
3. defer Close() patterns must check for errors
4. sync.Mutex fields must use pointer receivers
5. Use context.Context for cancellation and timeouts
6. Avoid init() functions when possible, prefer explicit initialization

## Style Notes
- Follow Effective Go conventions
- Use gofmt-compatible formatting
- Interface names should end with -er for single-method interfaces
- Package names should be short, lowercase, single-word
