#!/usr/bin/env bash
# Run a command on the aedo WORKER droplet and append it to remote_history.log.
# The worker has no public IP; it's reached via the web droplet as an SSH
# ProxyJump bastion (see the 'aedo-worker' Host entry in ~/.ssh/config).
# Usage: deploy/run_remote_worker.sh '<command>'
set -u

HOST="aedo-worker"
LOG="$(dirname "$0")/remote_history.log"

CMD="$1"
ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 "$HOST" "$CMD"
STATUS=$?
printf '%s | exit %d | [worker] %s\n' "$(date -u '+%Y-%m-%d %H:%M:%S UTC')" "$STATUS" "$CMD" >> "$LOG"
exit $STATUS
