#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
#  SAAS SENDBID — Disk monitoring script
#  Sends alert when disk usage exceeds threshold.
#  Schedule: every 15 minutes via cron (*/15 * * * *)
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

UPLOAD_DIR="${UPLOAD_DIR:-/var/app/uploads}"
THRESHOLD="${DISK_THRESHOLD:-80}"
ALERT_EMAIL="${ALERT_EMAIL:-admin@sendbid.com}"
SLACK_WEBHOOK="${SLACK_WEBHOOK:-}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# ── Get disk usage
DISK_PERCENT=$(df -h "$UPLOAD_DIR" | awk 'NR==2 {gsub(/%/,""); print $5}')
DISK_INFO=$(df -h "$UPLOAD_DIR" | awk 'NR==2 {print $2, $3, $4, $5}')

log "Disk check: ${DISK_PERCENT}% used (threshold: ${THRESHOLD}%)"
log "Total/Used/Free/Percent: $DISK_INFO"

# Per-category sizes
for cat in avatars kyc receipts; do
    if [ -d "$UPLOAD_DIR/$cat" ]; then
        SIZE=$(du -sh "$UPLOAD_DIR/$cat" 2>/dev/null | cut -f1)
        COUNT=$(find "$UPLOAD_DIR/$cat" -type f | wc -l)
        log "  $cat: $SIZE ($COUNT files)"
    fi
done

# ── Alert if threshold exceeded
if [ "$DISK_PERCENT" -ge "$THRESHOLD" ]; then
    MESSAGE="ALERT: SENDBID storage disk at ${DISK_PERCENT}% (threshold: ${THRESHOLD}%). Free: $(echo $DISK_INFO | awk '{print $3}')."

    log "ALERT: $MESSAGE"

    # Email alert
    if command -v mail &>/dev/null && [ -n "$ALERT_EMAIL" ]; then
        echo "$MESSAGE" | mail -s "[SENDBID] Disk space alert" "$ALERT_EMAIL"
    fi

    # Slack alert
    if [ -n "$SLACK_WEBHOOK" ]; then
        curl -s -X POST "$SLACK_WEBHOOK" \
            -H 'Content-type: application/json' \
            -d "{\"text\": \"$MESSAGE\"}" || true
    fi

    exit 2  # Exit code 2 = alert triggered
fi

log "Disk usage OK (${DISK_PERCENT}% < ${THRESHOLD}%)"
exit 0
