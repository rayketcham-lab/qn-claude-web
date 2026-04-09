# WebSocket Event Schemas

All events use Socket.IO. Auth is checked on every event via `_ws_auth_check()`.

## Client -> Server

### `terminal_create`
Create a new terminal session.
```json
{ "project_path": "/opt/my-project" }
```
**Response** emits `terminal_created`:
```json
{ "id": "abc123", "tmux_session": "qn-abcdef01" }
```

### `terminal_input`
Send keystrokes to a terminal.
```json
{ "id": "abc123", "data": "ls -la\r" }
```
Data field max: 64 KB.

### `terminal_resize`
Resize terminal dimensions.
```json
{ "id": "abc123", "cols": 120, "rows": 40 }
```

### `terminal_kill`
Kill an active terminal (detaches PTY, keeps tmux).
```json
{ "id": "abc123" }
```

### `terminal_detach`
Detach from a terminal without killing it.
```json
{ "id": "abc123" }
```

### `terminal_reconnect`
Reconnect to a detached tmux session.
```json
{ "tmux_session": "qn-abcdef01", "project_path": "/opt/my-project" }
```
**Response** emits `terminal_created` (same shape as `terminal_create`).

### `terminal_kill_tmux`
Kill a detached tmux session permanently.
```json
{ "tmux_session": "qn-abcdef01" }
```

### `terminal_list_detached`
List all detached sessions. No payload required.

**Response** emits `detached_sessions`:
```json
{
  "sessions": [
    { "name": "qn-abcdef01", "user": "admin", "updated": 1710000000 }
  ]
}
```

### `chat_message`
Send a chat message to Claude.
```json
{ "session_id": "sess-123", "message": "explain this code" }
```

### `claude_login`
Trigger Claude CLI login flow.
```json
{ "username": "admin" }
```

## Server -> Client

### `terminal_output`
Terminal output data (streamed).
```json
{ "id": "abc123", "data": "total 42\n..." }
```

### `terminal_created`
Confirms terminal creation or reconnection.
```json
{ "id": "abc123", "tmux_session": "qn-abcdef01" }
```

### `terminal_exited`
Terminal process has exited.
```json
{ "id": "abc123", "code": 0 }
```

### `terminal_error`
Error response for any terminal operation.
```json
{ "error": "Session belongs to another user" }
```

### `detached_sessions`
List of available detached sessions.
```json
{ "sessions": [{ "name": "...", "user": "...", "updated": 0 }] }
```

### `chat_response`
Streamed chat response from Claude.
```json
{ "session_id": "sess-123", "content": "Here's what...", "done": false }
```

### `chat_error`
Chat error.
```json
{ "session_id": "sess-123", "error": "Claude CLI not found" }
```
