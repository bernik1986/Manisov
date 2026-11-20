#!/usr/bin/env bash
set -Eeuo pipefail
# Install as /usr/local/bin/manisov-auto-deploy.sh after reviewing the runbook.
# systemd supplies /etc/manisov/deploy.env; this wrapper never sources shell secrets.
unset DEPLOY_SHA
exec /bin/bash /usr/local/lib/manisov/deploy.sh --timer
