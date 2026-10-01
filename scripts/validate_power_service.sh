#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# One reviewed update and guarded hardware trial. No autostart or package changes.
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
trial_python=${1:?Provide the prepared Python 3.12 interpreter}
bundle=${2:?Provide the reviewed staged service bundle or --installed}
[ "$(systemctl show gwe-fan-service.service -p ActiveState --value)" = inactive ] || {
    echo 'Installed service must be inactive before this update'; exit 1;
}
sudo -v
if [ "$bundle" = --installed ]; then
    sudo /usr/bin/python3 -I -B /opt/gwe-fan-service/entry.py check
else
    sudo sh "$bundle/update.sh"
fi
# The trial guard precedes service startup, so systemd has not necessarily
# created RuntimeDirectory yet. Never replace or chmod an existing path.
if sudo test ! -e /run/gwe-fan-service && sudo test ! -L /run/gwe-fan-service; then
    sudo install -d -o root -g root -m 0711 /run/gwe-fan-service
fi
cooler_was_active=0
if systemctl is-active --quiet coolercontrold.service; then cooler_was_active=1; fi
cleanup() {
    result=$?
    trap - EXIT
    if sudo systemctl stop gwe-fan-service.service &&
       sudo /usr/bin/python3 -I -B /opt/gwe-fan-service/entry.py recover &&
       sudo test ! -e /run/gwe-fan-service/owned.json &&
       sudo test ! -e /run/gwe-fan-service/power-pending.json &&
       sudo test ! -e /run/gwe-fan-service/power-trial.json; then
        if [ "$cooler_was_active" = 1 ]; then sudo systemctl start coolercontrold.service || result=1; fi
    else
        echo 'Recovery pending; CoolerControl remains stopped. Keep diagnostic records.'
        result=1
    fi
    exit "$result"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
sudo systemctl stop coolercontrold.service
sudo /usr/bin/python3 -I -B /opt/gwe-fan-service/entry.py prepare-power-trial
sudo systemctl start gwe-fan-service.service
"$trial_python" scripts/power_service_trial.py
