# /deploy — Deploy to Production

Deploy the current build to the production server.

## Usage
Invoke with: `/deploy` or `/deploy [version]`

## Process

1. **Pre-deploy Checks**:
   - Verify the server is currently running on port 5001
   - Run `install.sh --verify-only` to confirm file integrity
   - Check for uncommitted changes (warn if dirty)

2. **Service Restart**:
   - Kill the running server: `lsof -ti:5001 | xargs kill -9`
   - Wait 2 seconds for port release
   - Start the server: `/usr/bin/python3 /opt/claude-web/app.py`
   - Verify it comes up (check port 5001 is listening)

3. **Post-deploy Verification**:
   - Hit `/api/status` endpoint and verify response
   - Confirm version matches expected
   - Check for any startup errors in output

4. **tmux Session Preservation**: Verify that any existing tmux sessions (prefixed `qn-`) survived the restart.

## Output
```
# Deploy Report

**Version**: [version]
**Status**: SUCCESS / FAILED

## Steps
- [ ] Pre-flight passed
- [ ] Server stopped
- [ ] Server started
- [ ] Health check passed
- [ ] tmux sessions intact: [count]

## Errors
[any errors or warnings]
```
