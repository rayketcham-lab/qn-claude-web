# Hook Profile System

All hooks check `CLAUDE_HOOK_PROFILE` env var before executing.

## Profiles
- **full** (default): All hooks run normally
- **minimal**: Only PreCompact and SessionStart hooks run (safety-critical)
- **none**: All hooks are skipped (debugging only)

Set in settings.json env or shell: `export CLAUDE_HOOK_PROFILE=minimal`
