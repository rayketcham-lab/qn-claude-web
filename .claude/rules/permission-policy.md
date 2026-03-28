# Permission Policy

## No Blanket Permission Bypasses

**NEVER** use `skipDangerousModePermissionPrompt`, `dangerouslySkipPermissions`, or any global permission bypass in Claude Code settings — not in `~/.claude/settings.json`, not in project `settings.json`, not in `settings.local.json`.

All sessions must use the standard allow/deny/ask permission model. This applies to:
- Global user settings (`~/.claude/settings.json`)
- Project settings (`<project>/.claude/settings.json`)
- Local overrides (`<project>/.claude/settings.local.json`)

## How to Handle Permissions Correctly

- **allow**: Explicitly list tools and command patterns that are safe for the project
- **deny**: Explicitly block destructive or dangerous patterns
- **ask** (default): Everything not in allow/deny prompts for confirmation

## Project-Specific Permissions

Permissions that are specific to a project (e.g., pentest tools for the honeypot, database access for a specific app) go in that project's `settings.local.json` — NOT in the shared `/opt/claude/.claude/settings.local.json` or global user settings.

Use wildcards for command families rather than hardcoding individual commands:
- Good: `Bash(/home/<your-user>/pentest_exec.sh:*)`
- Bad: 30 individual `Bash(/home/<your-user>/pentest_exec.sh "nmap ...")` entries

## Why This Matters

Blanket bypasses silently remove the safety net across every session and every project. A pentest session shouldn't grant the same latitude as a documentation edit. Common-sense allow/deny rules scoped per-project keep the guardrails where they belong.
