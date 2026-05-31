#!/usr/bin/env bash
# Host-side watchdog (runs on the Proxmox host, NOT in the LXC).
# Curls the app health endpoint; on repeated failure remounts NFS and reboots
# the container, then emails. Mirrors the lunch-planner watchdog pattern.
set -uo pipefail

CTID="${CARCATCHER_CTID:-113}"            # CarCatcher LXC id — set in the unit env
HEALTH_URL="${CARCATCHER_HEALTH_URL:-http://192.168.178.0:8080/api/health}"
ALERT_EMAIL="${ALERT_EMAIL:-kai@jurtin.de}"
RETRIES="${RETRIES:-3}"
SLEEP_BETWEEN="${SLEEP_BETWEEN:-5}"

ok=0
for _ in $(seq 1 "$RETRIES"); do
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$HEALTH_URL" || echo 000)"
  if [[ "$code" == "200" ]]; then
    ok=1
    break
  fi
  sleep "$SLEEP_BETWEEN"
done

if [[ "$ok" == "1" ]]; then
  exit 0
fi

echo "[watchdog] CarCatcher unhealthy ($HEALTH_URL) — remount + reboot CT $CTID" >&2
mount -a || true
pct reboot "$CTID" || true

if command -v mail >/dev/null 2>&1; then
  echo "CarCatcher (CT $CTID) was unhealthy and has been rebooted at $(date)." \
    | mail -s "CarCatcher watchdog: rebooted CT $CTID" "$ALERT_EMAIL" || true
fi
