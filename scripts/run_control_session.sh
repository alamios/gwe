#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Explicit manual session. No profile migration, boot enablement or packages.
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
session_python=${1:?Provide the prepared Python 3.12 interpreter}
session_database=${2:?Provide the read-only backup database}
bundle=${3:?Provide the reviewed continuous-capable service bundle}
[ "$#" -eq 3 ] && [ -f "$session_database" ] || exit 1
unit=gwe-fan-service.service
override=/run/systemd/system/gwe-fan-service.service.d/90-gwe-continuous.conf
state=$(systemctl show "$unit" -p ActiveState --value)
case "$state" in inactive|failed) ;; *) echo 'Stop the experimental service first'; exit 1 ;; esac
sudo -v
if [ "$bundle" = --installed ]; then
    sudo test -f /opt/gwe-fan-service/continuous.conf || {
        echo 'Install the reviewed continuous-capable bundle first'; exit 1;
    }
else
    [ -f "$bundle/continuous.conf" ] && [ -f "$bundle/update.sh" ] || exit 1
fi
sudo test ! -e "$override" && sudo test ! -L "$override" || {
    echo 'Existing session override; review and recover it first'; exit 1;
}
sudo systemctl stop "$unit"
sudo /usr/bin/python3 -I -B /opt/gwe-fan-service/entry.py recover
for marker in owned.json power-pending.json power-trial.json; do
    sudo test ! -e "/run/gwe-fan-service/$marker" || exit 1
done
sudo systemctl reset-failed "$unit"
# Preserve older rollback copies instead of deleting them during repeat updates.
if [ "$bundle" != --installed ]; then
    if sudo test -e /opt/gwe-fan-service.previous || sudo test -L /opt/gwe-fan-service.previous; then
        sudo test -d /opt/gwe-fan-service.previous && sudo test ! -L /opt/gwe-fan-service.previous || exit 1
        archive="/opt/gwe-fan-service.previous.$(date -u +%Y%m%dT%H%M%SZ)"
        sudo test ! -e "$archive" && sudo test ! -L "$archive" || exit 1
        sudo mv -T -- /opt/gwe-fan-service.previous "$archive"
    fi
    sudo sh "$bundle/update.sh"
else
    sudo /usr/bin/python3 -I -B /opt/gwe-fan-service/entry.py check
    bundle=/opt/gwe-fan-service
fi
cooler_was_active=0
if systemctl is-active --quiet coolercontrold.service; then cooler_was_active=1; fi
override_installed=0
cleanup() {
    result=$?
    trap - EXIT
    recovered=0
    if sudo systemctl stop "$unit" &&
       sudo /usr/bin/python3 -I -B /opt/gwe-fan-service/entry.py recover; then
        recovered=1
        for marker in owned.json power-pending.json power-trial.json; do
            sudo test ! -e "/run/gwe-fan-service/$marker" || recovered=0
        done
    fi
    if [ "$override_installed" = 1 ]; then
        sudo rm -f -- "$override" || result=1
        sudo systemctl daemon-reload || result=1
    fi
    if [ "$recovered" = 1 ]; then
        if [ "$cooler_was_active" = 1 ]; then sudo systemctl start coolercontrold.service || result=1; fi
    else
        echo 'Recovery pending; leave CoolerControl stopped and retain records'
        result=1
    fi
    exit "$result"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
sudo systemctl stop coolercontrold.service
sudo install -d -o root -g root -m 0755 "$(dirname -- "$override")"
override_installed=1
sudo install -o root -g root -m 0644 "$bundle/continuous.conf" "$override"
sudo systemctl daemon-reload
sudo systemctl start "$unit"
"$session_python" scripts/run_service_gui.py --database "$session_database" \
    --allow-control --allow-power-control --continuous
