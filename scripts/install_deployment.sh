#!/usr/bin/env bash
# Explicit one-time administrator action. Does NOT start/enable any unit or deploy.
set -Eeuo pipefail
[[ "${ACK_TIMER_MIGRATION:-}" == yes && $EUID == 0 ]] || {
  echo "Read docs/DEPLOYMENT_HARDENING.md; run as root with ACK_TIMER_MIGRATION=yes." >&2; exit 2;
}
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f /etc/manisov/deploy.env ]] || { echo "Create protected /etc/manisov/deploy.env first." >&2; exit 1; }
[[ "$(stat -c %a /etc/manisov/deploy.env)" == 600 && "$(stat -c %u /etc/manisov/deploy.env)" == 0 ]]
if systemctl is-active --quiet manisov-deploy.timer || systemctl is-active --quiet manisov-deploy.service; then
  echo "Disable timer and wait for any existing deployment to finish before installation." >&2; exit 1
fi
exec 9>/var/lock/manisov-deploy.lock
flock -n 9
install -d -m 700 /var/lib/manisov-deploy /etc/manisov /usr/local/lib/manisov/scripts
install -m 700 "$root/deploy.sh" /usr/local/lib/manisov/deploy.sh
install -m 600 "$root/scripts/deployment_ci.py" "$root/scripts/deployment_data.py" /usr/local/lib/manisov/scripts/
install -m 700 "$root/scripts/deploy_timer.sh" /usr/local/bin/manisov-auto-deploy.sh
install -m 644 "$root/scripts/deployment/manisov-release@.service" "$root/scripts/deployment/manisov-deploy.service" /etc/systemd/system/
systemctl daemon-reload
echo "Installed only. Inspect systemctl cat manisov-deploy.timer and both services before enabling."
