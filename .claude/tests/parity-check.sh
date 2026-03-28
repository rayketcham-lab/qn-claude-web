#!/bin/bash
set -euo pipefail
# parity-check.sh — Detect drift between Linux and Windows configurations
# Fails CI if platforms diverge on shared concerns.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  FAIL: $1"; }

LINUX="$PROJECT_ROOT/settings-template.json"
WINDOWS="$PROJECT_ROOT/windows-setup/settings.json"

echo "=== Platform Parity Check ==="
echo ""

# ── 1. Shared permissions must match ──
echo "--- 1. Permission allow-list parity ---"

LINUX_ALLOW=$(jq -r '.permissions.allow[]' "$LINUX" | sort)
WINDOWS_ALLOW=$(jq -r '.permissions.allow[]' "$WINDOWS" | sort)

LINUX_ONLY=$(comm -23 <(echo "$LINUX_ALLOW") <(echo "$WINDOWS_ALLOW"))
WINDOWS_ONLY=$(comm -13 <(echo "$LINUX_ALLOW") <(echo "$WINDOWS_ALLOW"))

if [ -n "$LINUX_ONLY" ]; then
    fail "Permissions in Linux but not Windows: $LINUX_ONLY"
else
    pass "No Linux-only permissions"
fi

if [ -n "$WINDOWS_ONLY" ]; then
    fail "Permissions in Windows but not Linux: $WINDOWS_ONLY"
else
    pass "No Windows-only permissions"
fi

# ── 2. Shared deny rules (cross-platform ones) ──
echo ""
echo "--- 2. Cross-platform deny rules ---"

# These deny rules should exist on BOTH platforms (not platform-specific ones like sudo/del)
SHARED_DENY_PATTERNS=(
    "git push --force"
    "git push -f"
    "git commit --no-verify"
    "git reset --hard"
    "git clean -f"
    "git stash drop"
    "git stash clear"
    "Read(./.env)"
    "Write(./.env)"
    "Edit(./.env)"
    "Read(./secrets/"
    "Read(./**/*.pem)"
    "Read(./**/*.key)"
)

for pattern in "${SHARED_DENY_PATTERNS[@]}"; do
    LINUX_HAS=$(jq -r ".permissions.deny[]" "$LINUX" | grep -cF "$pattern" || true)
    WINDOWS_HAS=$(jq -r ".permissions.deny[]" "$WINDOWS" | grep -cF "$pattern" || true)
    if [ "$LINUX_HAS" -gt 0 ] && [ "$WINDOWS_HAS" -gt 0 ]; then
        pass "Both deny: $pattern"
    elif [ "$LINUX_HAS" -eq 0 ] && [ "$WINDOWS_HAS" -eq 0 ]; then
        fail "Neither denies: $pattern"
    elif [ "$LINUX_HAS" -eq 0 ]; then
        fail "Linux missing deny: $pattern"
    else
        fail "Windows missing deny: $pattern"
    fi
done

# ── 3. Env vars parity ──
echo ""
echo "--- 3. Environment variables ---"

SHARED_ENV_KEYS=("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS" "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE" "CLAUDE_HOOK_PROFILE")
for key in "${SHARED_ENV_KEYS[@]}"; do
    LINUX_VAL=$(jq -r ".env.$key // empty" "$LINUX")
    WINDOWS_VAL=$(jq -r ".env.$key // empty" "$WINDOWS")
    if [ -z "$LINUX_VAL" ] && [ -z "$WINDOWS_VAL" ]; then
        fail "Neither has env.$key"
    elif [ -z "$LINUX_VAL" ]; then
        fail "Linux missing env.$key (Windows=$WINDOWS_VAL)"
    elif [ -z "$WINDOWS_VAL" ]; then
        fail "Windows missing env.$key (Linux=$LINUX_VAL)"
    elif [ "$LINUX_VAL" = "$WINDOWS_VAL" ]; then
        pass "env.$key matches ($LINUX_VAL)"
    else
        fail "env.$key differs: Linux=$LINUX_VAL Windows=$WINDOWS_VAL"
    fi
done

# ── 4. Hook event coverage ──
echo ""
echo "--- 4. Hook event parity ---"

REQUIRED_EVENTS=("PreCompact" "Stop" "SessionEnd" "PostToolUse")
for event in "${REQUIRED_EVENTS[@]}"; do
    LINUX_HAS=$(jq -e ".hooks.$event" "$LINUX" > /dev/null 2>&1 && echo "yes" || echo "no")
    WINDOWS_HAS=$(jq -e ".hooks.$event" "$WINDOWS" > /dev/null 2>&1 && echo "yes" || echo "no")
    if [ "$LINUX_HAS" = "yes" ] && [ "$WINDOWS_HAS" = "yes" ]; then
        pass "Both have $event hook"
    elif [ "$LINUX_HAS" = "no" ] && [ "$WINDOWS_HAS" = "no" ]; then
        fail "Neither has $event hook"
    elif [ "$LINUX_HAS" = "no" ]; then
        fail "Linux missing $event hook"
    else
        fail "Windows missing $event hook"
    fi
done

# ── 5. Plugin parity ──
echo ""
echo "--- 5. Enabled plugins ---"

LINUX_PLUGINS=$(jq -r '.enabledPlugins | keys[]' "$LINUX" | sort)
WINDOWS_PLUGINS=$(jq -r '.enabledPlugins | keys[]' "$WINDOWS" | sort)

LINUX_ONLY_P=$(comm -23 <(echo "$LINUX_PLUGINS") <(echo "$WINDOWS_PLUGINS"))
WINDOWS_ONLY_P=$(comm -13 <(echo "$LINUX_PLUGINS") <(echo "$WINDOWS_PLUGINS"))

if [ -n "$LINUX_ONLY_P" ]; then
    fail "Plugins in Linux only: $LINUX_ONLY_P"
else
    pass "No Linux-only plugins"
fi
if [ -n "$WINDOWS_ONLY_P" ]; then
    fail "Plugins in Windows only: $WINDOWS_ONLY_P"
else
    pass "No Windows-only plugins"
fi

# ── 6. context-store.py security parity ──
echo ""
echo "--- 6. context-store.py parity ---"

LINUX_CS="$PROJECT_ROOT/mcp-servers/context-store.py"
WINDOWS_CS="$PROJECT_ROOT/windows-setup/context-store.py"

if grep -q 'safe_query' "$LINUX_CS" && grep -q 'safe_query' "$WINDOWS_CS"; then
    pass "Both have FTS5 sanitization"
else
    if ! grep -q 'safe_query' "$LINUX_CS"; then fail "Linux context-store.py missing FTS5 sanitization"; fi
    if ! grep -q 'safe_query' "$WINDOWS_CS"; then fail "Windows context-store.py missing FTS5 sanitization"; fi
fi

if grep -q 'ESCAPE' "$LINUX_CS" && grep -q 'ESCAPE' "$WINDOWS_CS"; then
    pass "Both have LIKE wildcard escaping"
else
    if ! grep -q 'ESCAPE' "$LINUX_CS"; then fail "Linux context-store.py missing LIKE escaping"; fi
    if ! grep -q 'ESCAPE' "$WINDOWS_CS"; then fail "Windows context-store.py missing LIKE escaping"; fi
fi

# ── 7. Rules parity ──
echo ""
echo "--- 7. Rules parity ---"

LINUX_RULES=$(ls "$PROJECT_ROOT/.claude/rules/"*.md 2>/dev/null | xargs -I{} basename {} | sort)
WINDOWS_RULES=$(ls "$PROJECT_ROOT/windows-setup/rules/"*.md 2>/dev/null | xargs -I{} basename {} | sort)

if [ "$LINUX_RULES" = "$WINDOWS_RULES" ]; then
    pass "Rule files match across platforms"
else
    fail "Rule files differ: Linux=$(echo "$LINUX_RULES" | tr '\n' ',') Windows=$(echo "$WINDOWS_RULES" | tr '\n' ',')"
fi

# ── 8. Hook scripts — functional coverage ──
# Names differ by design (Linux consolidates lint-dispatch; Windows uses separate scripts).
# Check that both platforms cover the same functional areas.
echo ""
echo "--- 8. Hook functional coverage ---"

# Shared hooks (same name both platforms)
SHARED_HOOKS=("hook-guard" "pre-compact-save" "session-end-save" "session-start" "stop-check" "context-monitor")
for hook in "${SHARED_HOOKS[@]}"; do
    LINUX_HAS=$(ls "$PROJECT_ROOT/hooks/$hook.sh" 2>/dev/null | wc -l)
    WINDOWS_HAS=$(ls "$PROJECT_ROOT/windows-setup/hooks/$hook.ps1" 2>/dev/null | wc -l)
    if [ "$LINUX_HAS" -gt 0 ] && [ "$WINDOWS_HAS" -gt 0 ]; then
        pass "Both have $hook"
    elif [ "$LINUX_HAS" -eq 0 ]; then
        fail "Linux missing $hook"
    else
        fail "Windows missing $hook"
    fi
done

# Functional equivalents (different names, same purpose)
# Linux lint-dispatch.sh = Windows ruff-lint.ps1 + clippy-check.ps1
if [ -f "$PROJECT_ROOT/hooks/lint-dispatch.sh" ]; then
    if [ -f "$PROJECT_ROOT/windows-setup/hooks/ruff-lint.ps1" ] && \
       [ -f "$PROJECT_ROOT/windows-setup/hooks/clippy-check.ps1" ]; then
        pass "Lint dispatch: Linux=lint-dispatch.sh, Windows=ruff-lint.ps1+clippy-check.ps1"
    else
        fail "Windows missing lint equivalent (need ruff-lint.ps1 and clippy-check.ps1)"
    fi
fi

# Linux clippy-batch.sh = Windows stop-verify.ps1
if [ -f "$PROJECT_ROOT/hooks/clippy-batch.sh" ]; then
    if [ -f "$PROJECT_ROOT/windows-setup/hooks/stop-verify.ps1" ]; then
        pass "Stop verify: Linux=clippy-batch.sh, Windows=stop-verify.ps1"
    else
        fail "Windows missing stop-verify.ps1 (equivalent of clippy-batch.sh)"
    fi
fi


# ── 9. Skills and agents content parity ──
echo ""
echo "--- 9. Skills/agents content parity ---"

# Compare shared skills (SKILL.md files)
while IFS= read -r -d '' skill_file; do
    rel_path="${skill_file#$PROJECT_ROOT/.claude/skills/}"
    win_file="$PROJECT_ROOT/windows-setup/skills/$rel_path"
    if [ -f "$win_file" ]; then
        if diff -q "$skill_file" "$win_file" > /dev/null 2>&1; then
            pass "Skill matches: $rel_path"
        else
            fail "Skill differs: $rel_path"
        fi
    else
        fail "Windows missing skill: $rel_path"
    fi
done < <(find "$PROJECT_ROOT/.claude/skills" -name "SKILL.md" -print0 2>/dev/null)

# Check for Windows-only skills not in Linux
while IFS= read -r -d '' skill_file; do
    rel_path="${skill_file#$PROJECT_ROOT/windows-setup/skills/}"
    linux_file="$PROJECT_ROOT/.claude/skills/$rel_path"
    if [ ! -f "$linux_file" ]; then
        fail "Linux missing skill: $rel_path"
    fi
done < <(find "$PROJECT_ROOT/windows-setup/skills" -name "SKILL.md" -print0 2>/dev/null)

# Compare shared agents
while IFS= read -r -d '' agent_file; do
    name="$(basename "$agent_file")"
    win_file="$PROJECT_ROOT/windows-setup/agents/$name"
    if [ -f "$win_file" ]; then
        if diff -q "$agent_file" "$win_file" > /dev/null 2>&1; then
            pass "Agent matches: $name"
        else
            fail "Agent differs: $name"
        fi
    else
        fail "Windows missing agent: $name"
    fi
done < <(find "$PROJECT_ROOT/.claude/agents" -name "*.md" -print0 2>/dev/null)

while IFS= read -r -d '' agent_file; do
    name="$(basename "$agent_file")"
    linux_file="$PROJECT_ROOT/.claude/agents/$name"
    if [ ! -f "$linux_file" ]; then
        fail "Linux missing agent: $name"
    fi
done < <(find "$PROJECT_ROOT/windows-setup/agents" -name "*.md" -print0 2>/dev/null)

# ── Summary ──
echo ""
echo "==========================================="
echo "Parity: $PASS passed, $FAIL failed"
echo "==========================================="

if [ "$FAIL" -gt 0 ]; then
    echo "PARITY CHECK FAILED — platforms have diverged"
    exit 1
else
    echo "PLATFORMS IN SYNC"
    exit 0
fi
