---
name: secreview
description: Quick security review of a file, component, or change. Runs input validation audit, crypto review, dependency scan, secret detection, and access control checks.
argument-hint: "[file, component, or description]"
user_invocable: true
tools: Read, Glob, Grep, WebSearch
---

# /secreview — Quick Security Review

Run a focused SecOps review of the current change.

## Process
As the SecOps agent, perform:

1. **Input Validation Audit**: Check all trust boundaries for proper sanitization
2. **Crypto Review**: Verify algorithm choices, key management, certificate handling
3. **Dependency Scan**: Check for known CVEs in any new or updated dependencies
4. **Secret Detection**: Scan for hardcoded credentials, keys, tokens
5. **Access Control**: Verify authorization checks are present and correct

## Target
$ARGUMENTS

## Output
```
# Security Review: [Subject]

**Risk Level**: CRITICAL / HIGH / MEDIUM / LOW
**Blocking Issues**: [count]

## Findings
[numbered findings with severity, impact, and remediation]

## Approved / Blocked
[decision with conditions if applicable]
```
