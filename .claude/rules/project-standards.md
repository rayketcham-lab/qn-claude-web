# Project Standards

- No warnings in CI. Error handling mandatory. Functions >50 lines → decompose.
- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `ci:`, `security:`
- No secrets in code. Input validation at trust boundaries.
- Dependencies audited before adoption — check for CVEs, maintenance status, license.
- New features/bug fixes require tests. Security code requires adversarial tests.
- Prefer editing existing files over creating new ones.
