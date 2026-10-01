#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu
[ "$(id -u)" -eq 0 ] || { echo 'Administrator privileges required'; exit 1; }
systemctl stop gwe-fan-service.service
for marker in /run/gwe-fan-service/owned.json /run/gwe-fan-service/power-pending.json /run/gwe-fan-service/power-trial.json; do
    [ ! -e "$marker" ] && [ ! -L "$marker" ] || {
        echo 'Recovery unresolved; refusing removal. Keep the service files for recovery.'; exit 1;
    }
done
rm -f -- /etc/systemd/system/gwe-fan-service.service
systemctl daemon-reload
rm -rf -- /opt/gwe-fan-service
printf '%s\n' 'Removed service code/unit. Private configuration and runtime directory were preserved.'
