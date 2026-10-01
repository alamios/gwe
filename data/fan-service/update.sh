#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Reviewed bundle update; preserves configuration and a rollback copy. Never starts.
set -eu
[ "$(id -u)" -eq 0 ] || { echo 'Administrator privileges required'; exit 1; }
cd -- "$(dirname -- "$0")"
sha256sum --check --strict SHA256SUMS
[ "$(systemctl show gwe-fan-service.service -p ActiveState --value)" = inactive ] || {
    echo 'Stop and verify the installed service before updating'; exit 1;
}
for marker in /run/gwe-fan-service/owned.json /run/gwe-fan-service/power-pending.json /run/gwe-fan-service/power-trial.json /run/gwe-fan-service/session.json; do
    [ ! -e "$marker" ] && [ ! -L "$marker" ] || { echo 'Recovery pending; refusing update'; exit 1; }
done
for target in /opt/gwe-fan-service /etc/systemd/system/gwe-fan-service.service /etc/gwe-fan-service.json; do
    [ -e "$target" ] && [ ! -L "$target" ] || { echo 'Expected regular installation missing'; exit 1; }
done
[ ! -e /opt/gwe-fan-service.previous ] && [ ! -L /opt/gwe-fan-service.previous ] || {
    echo 'Previous rollback copy exists; retain/review it before another update'; exit 1;
}
[ ! -e /opt/gwe-fan-service.next ] && [ ! -L /opt/gwe-fan-service.next ] || exit 1
install -d -o root -g root -m 0755 /opt/gwe-fan-service.next/lib/gwe
committed=0
rollback() {
    if [ "$committed" -eq 0 ]; then
        if [ -d /opt/gwe-fan-service.previous ]; then
            rm -rf /opt/gwe-fan-service
            mv /opt/gwe-fan-service.previous /opt/gwe-fan-service
            cp /opt/gwe-fan-service/unit.before-update /etc/systemd/system/gwe-fan-service.service
            systemctl daemon-reload || true
        fi
        rm -rf /opt/gwe-fan-service.next
    fi
}
trap rollback EXIT
trap 'exit 1' HUP INT TERM
for module in fan_curve fan_service fan_process fan_daemon nvml_fan_control nvml_power power_process power_trial __init__; do
    install -o root -g root -m 0644 "lib/gwe/$module.py" "/opt/gwe-fan-service.next/lib/gwe/$module.py"
done
install -o root -g root -m 0644 lib/pynvml.py /opt/gwe-fan-service.next/lib/pynvml.py
for name in entry.py COPYING.txt BINDING_VERSION uninstall.sh; do
    install -o root -g root -m 0644 "$name" "/opt/gwe-fan-service.next/$name"
done
if [ -f continuous.conf ]; then
    install -o root -g root -m 0644 continuous.conf /opt/gwe-fan-service.next/continuous.conf
fi
install -o root -g root -m 0644 /etc/systemd/system/gwe-fan-service.service /opt/gwe-fan-service/unit.before-update
mv /opt/gwe-fan-service /opt/gwe-fan-service.previous
mv /opt/gwe-fan-service.next /opt/gwe-fan-service
# The entry point accepts only the final trusted installation path. Validate
# after the swap while the rollback trap still protects the previous code/unit.
/usr/bin/python3 -I -B /opt/gwe-fan-service/entry.py check
install -o root -g root -m 0644 gwe-fan-service.service /etc/systemd/system/gwe-fan-service.service
systemctl daemon-reload
committed=1
printf '%s\n' 'Updated, not started or enabled. Configuration preserved; previous code and unit retained.'
