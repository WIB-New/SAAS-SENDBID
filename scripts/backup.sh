#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
#  SAAS SENDBID — Backup script
#  Uses restic to back up /var/app/uploads to a remote/secondary location.
#  Schedule: daily via systemd timer or cron (0 2 * * *)
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Configuration
UPLOAD_DIR="${UPLOAD_DIR:-/var/app/uploads}"
RESTIC_REPO="${RESTIC_REPO:-sftp:backup@192.168.1.100:/backups/sendbid-storage}"
RESTIC_PASSWORD_FILE="${RESTIC_PASSWORD_FILE:-/etc/sendbid/restic-password}"
LOG_FILE="/var/log/sendbid/backup.log"
SLACK_WEBHOOK="${SLACK_WEBHOOK:-}"  # Optional

# Retention policy
KEEP_DAILY=7
KEEP_WEEKLY=4
KEEP_MONTHLY=3

# ── Logging
mkdir -p "$(dirname "$LOG_FILE")"
exec >> "$LOG_FILE" 2>&1

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

notify() {
    local status="$1"
    local message="$2"
    log "$message"
    if [ -n "$SLACK_WEBHOOK" ]; then
        curl -s -X POST "$SLACK_WEBHOOK" \
            -H 'Content-type: application/json' \
            -d "{\"text\": \"[SENDBID Backup] $status: $message\"}" || true
    fi
}

# ── Backup
log "=== Starting SENDBID backup ==="
log "Source: $UPLOAD_DIR"
log "Destination: $RESTIC_REPO"

if ! command -v restic &>/dev/null; then
    notify "ERROR" "restic not found. Install with: apt install restic"
    exit 1
fi

# Initialize repo if needed
export RESTIC_REPOSITORY="$RESTIC_REPO"
export RESTIC_PASSWORD_FILE="$RESTIC_PASSWORD_FILE"

if ! restic snapshots &>/dev/null; then
    log "Initializing restic repository..."
    restic init
fi

# Run backup
if restic backup \
    --verbose \
    --tag "sendbid" \
    --tag "$(date '+%Y-%m-%d')" \
    "$UPLOAD_DIR"; then
    notify "OK" "Backup completed successfully"
else
    notify "ERROR" "Backup FAILED"
    exit 1
fi

# Apply retention policy
log "Applying retention: daily=$KEEP_DAILY, weekly=$KEEP_WEEKLY, monthly=$KEEP_MONTHLY"
restic forget \
    --keep-daily "$KEEP_DAILY" \
    --keep-weekly "$KEEP_WEEKLY" \
    --keep-monthly "$KEEP_MONTHLY" \
    --prune

# Verify integrity
log "Verifying backup integrity..."
if restic check --read-data-subset=5%; then
    log "Integrity check passed"
else
    notify "WARNING" "Integrity check had warnings — check logs"
fi

log "=== Backup complete ==="

# ── Alternative: rsync (simpler, no encryption)
# Uncomment to use rsync instead of restic:
# rsync -avz --delete \
#     "$UPLOAD_DIR/" \
#     "backup@192.168.1.100:/backups/sendbid-storage/" \
#     --exclude="*.tmp"
