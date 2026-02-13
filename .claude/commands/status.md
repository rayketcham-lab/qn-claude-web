# /status — System Status Dashboard

Show a comprehensive status of the QN Code Assistant system.

## Usage
Invoke with: `/status`

## Process
Gather and report on all of the following:

1. **Server Status**:
   - Check if port 5001 is listening (`lsof -ti:5001`)
   - Hit `/api/status` for uptime, version, active terminals
   - Check systemd service status (`systemctl status qn-code-assistant`)

2. **Git State**:
   - Current branch and last commit
   - Uncommitted changes count
   - Ahead/behind remote

3. **tmux Sessions**:
   - List all `qn-*` tmux sessions with their status
   - Show which are attached vs detached

4. **CI/CD**:
   - Last GitHub Actions workflow run status (use `gh run list --limit 3`)
   - Self-hosted runner status

5. **Tests**:
   - Run unit tests and report pass/fail count
   - Note last integration test result if available

6. **Disk & Resources**:
   - Project directory size
   - Session logs count and size
   - Agent logs count

## Output
```
# System Status — [timestamp]

| Component | Status |
|-----------|--------|
| Server | [running/stopped] on :5001 |
| Version | [version] |
| Git | [branch] — [clean/dirty] |
| tmux | [count] sessions |
| CI | [last run status] |
| Tests | [pass/fail] |
| Disk | [size] |
```
