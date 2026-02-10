#!/bin/bash
#
# QN Code Assistant - Maintenance Script
# Run via cron: 0 4 * * * /opt/claude-web/maintenance.sh
#

set -e
cd "$(dirname "$0")"

LOG_FILE="/var/log/qn-code-assistant-maintenance.log"
BACKUP_DIR="./backups"
SESSIONS_DIR="./sessions"
MAX_BACKUPS=7

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Starting maintenance ==="

# 1. Backup sessions
log "Backing up sessions..."
mkdir -p "$BACKUP_DIR"
BACKUP_NAME="sessions-$(date '+%Y%m%d-%H%M%S').tar.gz"
if [ -d "$SESSIONS_DIR" ] && [ "$(ls -A $SESSIONS_DIR 2>/dev/null)" ]; then
    tar -czf "$BACKUP_DIR/$BACKUP_NAME" -C "$SESSIONS_DIR" .
    log "Created backup: $BACKUP_NAME"
else
    log "No sessions to backup"
fi

# 2. Rotate old backups (keep last 7)
log "Rotating old backups..."
cd "$BACKUP_DIR"
ls -t sessions-*.tar.gz 2>/dev/null | tail -n +$((MAX_BACKUPS + 1)) | xargs -r rm -f
cd - > /dev/null
log "Backup rotation complete"

# 3. Trigger API cleanup
log "Triggering process cleanup..."
curl -s -X POST http://localhost:5001/api/maintenance/cleanup || log "Warning: Could not reach cleanup API"

# 4. Check for Claude Code updates
log "Checking for Claude Code updates..."
if command -v claude &> /dev/null; then
    # Run update check
    claude update 2>&1 | tee -a "$LOG_FILE" || log "Warning: Claude update check failed"
else
    log "Warning: claude command not found"
fi

# 5. Check disk space
DISK_USAGE=$(df -h . | awk 'NR==2 {print $5}' | tr -d '%')
if [ "$DISK_USAGE" -gt 90 ]; then
    log "WARNING: Disk usage is ${DISK_USAGE}%!"
fi

# 6. Clean up old log entries (keep last 1000 lines)
if [ -f "$LOG_FILE" ]; then
    tail -1000 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
fi

log "=== Maintenance complete ==="
