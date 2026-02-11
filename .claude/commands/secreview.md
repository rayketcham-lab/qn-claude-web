# /secreview — Quick Security Review

Run a focused SecOps review of the current change.

## Usage
Invoke with: `/secreview [file, component, or description]`

## Process
As the SecOps agent, perform:

1. **Input Validation Audit**: Check all trust boundaries for proper sanitization
2. **Crypto Review**: Verify algorithm choices, key management, certificate handling
3. **Dependency Scan**: Check for known CVEs in any new or updated dependencies
4. **Secret Detection**: Scan for hardcoded credentials, keys, tokens
5. **Access Control**: Verify authorization checks are present and correct

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
