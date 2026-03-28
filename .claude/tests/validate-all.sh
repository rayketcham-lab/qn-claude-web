#!/bin/bash
set -euo pipefail
# validate-all.sh — Comprehensive validation for the Claude Code orchestrator
# Run: bash .claude/tests/validate-all.sh
# Use as pre-commit hook or CI check

PASS=0
FAIL=0
WARN=0

pass() { PASS=$((PASS + 1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  FAIL: $1"; }
warn() { WARN=$((WARN + 1)); echo "  WARN: $1"; }

# Resolve project root (script lives in .claude/tests/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Claude Code Orchestrator Validation ==="
echo "Project: $PROJECT_ROOT"
echo ""

# ─────────────────────────────────────────────
echo "--- 1. JSON Validity ---"
# ─────────────────────────────────────────────

for f in "$PROJECT_ROOT/.claude/settings.json"; do
  if [[ -f "$f" ]]; then
    if jq . "$f" > /dev/null 2>&1; then
      pass "$(basename "$f") is valid JSON"
    else
      fail "$(basename "$f") is INVALID JSON"
    fi
  else
    warn "$(basename "$f") not found"
  fi
done

# User-level settings
if [[ -f "$HOME/.claude/settings.json" ]]; then
  if jq . "$HOME/.claude/settings.json" > /dev/null 2>&1; then
    pass "User settings.json is valid JSON"
  else
    fail "User settings.json is INVALID JSON"
  fi
fi

# ─────────────────────────────────────────────
echo ""
echo "--- 2. Settings Schema Checks ---"
# ─────────────────────────────────────────────

SETTINGS="$PROJECT_ROOT/.claude/settings.json"
if [[ -f "$SETTINGS" ]]; then
  # Deny/ask rules live in user-level settings (gitignored), not project settings.
  # Check the settings-template.json instead, which defines what SHOULD be deployed.
  TEMPLATE="$PROJECT_ROOT/settings-template.json"
  if [[ -f "$TEMPLATE" ]]; then
    DENY_COUNT=$(jq '.permissions.deny | length' "$TEMPLATE" 2>/dev/null || echo "0")
    if [[ "$DENY_COUNT" -gt 0 ]]; then
      pass "Template deny rules present ($DENY_COUNT rules)"
    else
      warn "Template has no deny rules (expected in user settings)"
    fi

    if jq -e '.permissions.deny[] | select(test("rm -rf \\*"))' "$TEMPLATE" > /dev/null 2>&1; then
      pass "Template blocks rm -rf *"
    else
      warn "rm -rf * not in template deny list"
    fi

    if jq -e '.permissions.deny[] | select(test("git push.*-f|git push.*force"))' "$TEMPLATE" > /dev/null 2>&1; then
      pass "Template blocks force push"
    else
      warn "Force push not in template deny list"
    fi
  else
    warn "No settings-template.json found — cannot validate deny rules"
  fi

  # Check $schema present
  if jq -e '."$schema"' "$SETTINGS" > /dev/null 2>&1; then
    pass "\$schema field present"
  else
    warn "No \$schema field for editor validation"
  fi

  # Check autocompact env var (can be in project or template)
  AUTOCOMPACT_SET="no"
  if jq -e '.env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE' "$SETTINGS" > /dev/null 2>&1; then
    AUTOCOMPACT_SET="yes"
  elif [[ -f "$TEMPLATE" ]] && jq -e '.env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE' "$TEMPLATE" > /dev/null 2>&1; then
    AUTOCOMPACT_SET="yes"
  fi
  if [[ "$AUTOCOMPACT_SET" = "yes" ]]; then
    pass "Autocompact threshold configured"
  else
    warn "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE not set (defaults to 95%)"
  fi
fi

# ─────────────────────────────────────────────
echo ""
echo "--- 3. Agent Frontmatter ---"
# ─────────────────────────────────────────────

for agent_file in "$PROJECT_ROOT/.claude/agents/"*.md; do
  agent_name="$(basename "$agent_file" .md)"
  if head -1 "$agent_file" | grep -q "^---$"; then
    pass "$agent_name has YAML frontmatter"
    # Check for required fields
    if grep -q "^name:" "$agent_file"; then
      pass "$agent_name has name field"
    else
      fail "$agent_name missing name field"
    fi
    if grep -q "^description:" "$agent_file"; then
      pass "$agent_name has description field"
    else
      fail "$agent_name missing description field"
    fi
  else
    fail "$agent_name has NO frontmatter"
  fi
done

# ─────────────────────────────────────────────
echo ""
echo "--- 4. Skills/Commands ---"
# ─────────────────────────────────────────────

# Check skills directory
if [[ -d "$PROJECT_ROOT/.claude/skills" ]]; then
  SKILL_COUNT=$(find "$PROJECT_ROOT/.claude/skills" -name "SKILL.md" | wc -l)
  pass "Skills directory present ($SKILL_COUNT skills)"

  for skill_file in "$PROJECT_ROOT/.claude/skills/"*/SKILL.md; do
    skill_name="$(basename "$(dirname "$skill_file")")"
    if head -1 "$skill_file" | grep -q "^---$"; then
      pass "Skill $skill_name has frontmatter"
    else
      fail "Skill $skill_name missing frontmatter"
    fi
  done
else
  warn "No .claude/skills/ directory — using deprecated commands format"
fi

# Check legacy commands
if [[ -d "$PROJECT_ROOT/.claude/commands" ]]; then
  CMD_COUNT=$(find "$PROJECT_ROOT/.claude/commands" -name "*.md" | wc -l)
  if [[ -d "$PROJECT_ROOT/.claude/skills" ]]; then
    warn "Legacy commands/ still exists ($CMD_COUNT commands) — consider removing after skills migration"
  else
    warn "Using legacy commands/ ($CMD_COUNT commands) — migrate to skills/"
  fi
fi

# ─────────────────────────────────────────────
echo ""
echo "--- 5. Shell Scripts ---"
# ─────────────────────────────────────────────

if command -v shellcheck &>/dev/null; then
  for script in "$PROJECT_ROOT/scripts/"*.sh "$PROJECT_ROOT/link-agents.sh"; do
    if [[ -f "$script" ]]; then
      if shellcheck -S warning "$script" > /dev/null 2>&1; then
        pass "$(basename "$script") passes shellcheck"
      else
        warn "$(basename "$script") has shellcheck warnings"
      fi
    fi
  done

  # Check hook scripts if at user level
  for script in "$HOME/.claude/hooks/"*.sh; do
    if [[ -f "$script" ]]; then
      if shellcheck -S warning "$script" > /dev/null 2>&1; then
        pass "hook/$(basename "$script") passes shellcheck"
      else
        warn "hook/$(basename "$script") has shellcheck warnings"
      fi
    fi
  done
else
  warn "shellcheck not installed — skipping shell lint"
fi

# ─────────────────────────────────────────────
echo ""
echo "--- 6. Hookify Rules ---"
# ─────────────────────────────────────────────

HOOKIFY_COUNT=0
for rule in "$PROJECT_ROOT/.claude/"hookify.*.md; do
  if [[ -f "$rule" ]]; then
    HOOKIFY_COUNT=$((HOOKIFY_COUNT + 1))
    rule_name="$(basename "$rule")"
    if grep -q "^enabled: true" "$rule"; then
      pass "$rule_name enabled"
    else
      warn "$rule_name is DISABLED"
    fi
  fi
done

if [[ "$HOOKIFY_COUNT" -eq 0 ]]; then
  warn "No hookify rules found"
else
  pass "$HOOKIFY_COUNT hookify rules present"
fi

# Run hookify pattern tests if available
if [[ -f "$PROJECT_ROOT/.claude/tests/hookify-patterns-test.sh" ]]; then
  echo ""
  echo "--- 6b. Hookify Pattern Tests ---"
  if bash "$PROJECT_ROOT/.claude/tests/hookify-patterns-test.sh" 2>&1 | tail -2; then
    pass "Hookify pattern tests pass"
  else
    fail "Hookify pattern tests FAILED"
  fi
fi

# ─────────────────────────────────────────────
echo ""
echo "--- 7. CLAUDE.md ---"
# ─────────────────────────────────────────────

CLAUDE_MD="$PROJECT_ROOT/CLAUDE.md"
if [[ -f "$CLAUDE_MD" ]]; then
  LINE_COUNT=$(wc -l < "$CLAUDE_MD")
  CHAR_COUNT=$(wc -c < "$CLAUDE_MD")
  if [[ "$LINE_COUNT" -lt 500 ]]; then
    pass "CLAUDE.md is concise ($LINE_COUNT lines, $CHAR_COUNT chars)"
  else
    warn "CLAUDE.md is large ($LINE_COUNT lines) — consider trimming"
  fi
else
  fail "No CLAUDE.md found"
fi

# ─────────────────────────────────────────────
echo ""
echo "--- 8. Git Hygiene ---"
# ─────────────────────────────────────────────

if [[ -f "$PROJECT_ROOT/.gitignore" ]]; then
  pass ".gitignore present"
  if grep -q "\.env" "$PROJECT_ROOT/.gitignore"; then
    pass ".env in .gitignore"
  else
    fail ".env NOT in .gitignore"
  fi
  if grep -q "\.ruff_cache" "$PROJECT_ROOT/.gitignore"; then
    pass ".ruff_cache in .gitignore"
  else
    warn ".ruff_cache not in .gitignore"
  fi
  if grep -q "settings\.local\.json" "$PROJECT_ROOT/.gitignore"; then
    pass "settings.local.json in .gitignore"
  else
    warn "settings.local.json not in .gitignore"
  fi
else
  fail "No .gitignore found"
fi

# ─────────────────────────────────────────────
echo ""
echo "==========================================="
echo "Results: $PASS passed, $FAIL failed, $WARN warnings"
echo "==========================================="

if [[ "$FAIL" -gt 0 ]]; then
  echo "VALIDATION FAILED — fix the failures above"
  exit 1
elif [[ "$WARN" -gt 0 ]]; then
  echo "VALIDATION PASSED with warnings"
  exit 0
else
  echo "ALL CHECKS PASSED"
  exit 0
fi
