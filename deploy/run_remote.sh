#!/usr/bin/env bash
# Run a command on the voxshelf droplet and append it to remote_history.log.
# Usage: deploy/run_remote.sh '<command>'
set -u

HOST="root@206.189.163.67"
KEY="$HOME/.ssh/voxshelf_deploy"
LOG="$(dirname "$0")/remote_history.log"

CMD="$1"
ssh -i "$KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "$HOST" "$CMD"
STATUS=$?
printf '%s | exit %d | %s\n' "$(date -u '+%Y-%m-%d %H:%M:%S UTC')" "$STATUS" "$CMD" >> "$LOG"
exit $STATUS
