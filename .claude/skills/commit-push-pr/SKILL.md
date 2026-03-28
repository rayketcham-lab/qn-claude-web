---
name: commit-push-pr
description: Commit all changes, push to remote, and open a pull request in one shot. The most common inner-loop workflow.
user_invocable: true
tools: Read, Bash, Glob, Grep
model: inherit
---

# Commit → Push → PR

Execute the full commit-push-PR workflow in a single invocation.

## Steps

1. **Assess changes**: Run `git status` and `git diff --stat` to understand what's being committed
2. **Stage intelligently**: Add changed/new files by name (never `git add -A`). Skip `.env`, secrets, credentials, `.pem`, `.key` files.
3. **Craft commit message**: Follow conventional commit format (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `ci:`, `security:`). Focus on *why* not *what*. End with `Co-Authored-By: Claude <noreply@anthropic.com>`
4. **Push**: Push to the current branch with `-u` flag if no upstream is set. Create a new branch from current if on main/master.
5. **Open PR**: Use `gh pr create` with:
   - Short title (<70 chars)
   - Body with `## Summary` (1-3 bullets), `## Test plan` (checklist), and `Generated with Claude Code` footer
6. **Report**: Return the PR URL

## Safety Checks
- NEVER force push
- NEVER push directly to main/master — create a branch first
- NEVER commit files matching: `.env*`, `secrets/`, `credentials*`, `*.pem`, `*.key`
- If `gh` CLI is not available, commit and push but skip PR creation and tell the user

## Branch Naming
If creating a new branch, use: `claude/<type>/<short-description>`
- Example: `claude/feat/add-verification-hook`
- Example: `claude/fix/ocsp-response-parsing`
