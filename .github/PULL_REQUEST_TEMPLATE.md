## Summary

Briefly describe what this PR does and why.

Closes #<!-- issue number, if applicable -->

---

## Type of Change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that changes existing behavior)
- [ ] Refactor (no behavior change, code quality improvement)
- [ ] Security fix or hardening
- [ ] Documentation update
- [ ] CI/CD change

---

## Implementation Checklist

- [ ] Follows existing project patterns and conventions (see [CLAUDE.md](../CLAUDE.md))
- [ ] Error handling is comprehensive — no silent failures
- [ ] No hardcoded values that should be configurable
- [ ] No debug or temporary code left in
- [ ] No TODO/FIXME added without a linked issue

## Testing

- [ ] Existing tests pass: `python3 -m unittest discover -s tests -p 'test_*.py' -v`
- [ ] New or updated tests cover the changes
- [ ] Bug fixes include a regression test
- [ ] Security-sensitive code has adversarial test cases

## Security

- [ ] No secrets or credentials introduced in source or config
- [ ] Input validation added at any new trust boundaries
- [ ] Path handling uses `validate_file_path()` and the allowed-path enforcement
- [ ] Any new dependencies vetted for CVEs and license compatibility
- [ ] `build-installer.sh` re-run if any files changed (hash update)

## Documentation

- [ ] Public API changes documented
- [ ] README updated if user-visible behavior changed
- [ ] CLAUDE.md updated if architectural patterns changed

---

## Notes for Reviewer

Anything the reviewer should pay particular attention to, known edge cases, or areas of uncertainty.
