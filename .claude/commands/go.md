You are resuming work from a previous session. Follow these steps exactly:

1. **Read your auto memory MEMORY.md** — it contains your saved session state including what you were working on, what's done, and what's next.

2. **Assess the current state**:
   - Run `git status` to see the working tree
   - Check any files mentioned in MEMORY.md as "in progress"
   - Verify what's done vs what remains

3. **Resume working autonomously** from where you left off. Follow the "Next steps" or "Suggested Resume Order" in MEMORY.md.

4. **Work rules for this session**:
   - Work autonomously — do not ask "should I proceed?" or "would you like me to continue?" Just do the work.
   - When you hit a **decision point** (architecture choice, trade-off, ambiguity, multiple valid approaches), use **AskUserQuestion** with 2-4 concrete options. Include a recommended option. Frame the trade-offs clearly.
   - When you hit a **blocker** you genuinely cannot resolve, update MEMORY.md with `## Task Status: BLOCKED` and explain what's blocking.
   - When the task is **fully complete** (builds, tests pass, everything working), update MEMORY.md with `## Task Status: TASK_COMPLETE` and summarize what was built.
   - Before context gets heavy (sentinel ORANGE zone), save full state to MEMORY.md with what's done and what's next, then compact.

5. **Start working now.** Do not summarize the plan back to me. Just start doing the next thing on the list.
