# Shell Standards

- Always start with `set -euo pipefail`
- Quote all variables: `"$var"` not `$var`
- **NEVER use `&&`, `||`, or `;` in Bash tool calls** — these bypass permission prefix matching. Use separate commands instead.
- Use `[[ ]]` over `[ ]` for conditionals
- Use `$(command)` over backticks
- Prefer absolute paths in scripts
