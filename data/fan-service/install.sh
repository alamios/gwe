#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Run only after reviewing the staged bundle. No packages, start or enable.
set -eu
[ "$(id -u)" -eq 0 ] || { echo 'Administrator privileges required'; exit 1; }
cd -- "$(dirname -- "$0")"
sha256sum --check --strict SHA256SUMS
for target in /opt/gwe-fan-service /etc/systemd/system/gwe-fan-service.service /etc/gwe-fan-service.json; do
    if [ -e "$target" ] || [ -L "$target" ]; then
        printf '%s\n' 'Existing installation/configuration found; refusing overwrite.'
        exit 1
    fi
done
installation_done=0
cleanup() {
    if [ "$installation_done" -eq 0 ]; then
        rm -f -- /etc/systemd/system/gwe-fan-service.service /etc/gwe-fan-service.json
        rm -rf -- /opt/gwe-fan-service
        systemctl daemon-reload || true
    fi
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
# Refuse unknown files: install only the reviewed fixed file set.
install -d -o root -g root -m 0755 /opt/gwe-fan-service/lib/gwe
for module in fan_curve fan_service fan_process fan_daemon nvml_fan_control nvml_power power_process power_trial __init__; do
    install -o root -g root -m 0644 "lib/gwe/$module.py" "/opt/gwe-fan-service/lib/gwe/$module.py"
done
install -o root -g root -m 0644 lib/pynvml.py /opt/gwe-fan-service/lib/pynvml.py
for name in entry.py COPYING.txt BINDING_VERSION uninstall.sh; do
    install -o root -g root -m 0644 "$name" "/opt/gwe-fan-service/$name"
done
install -o root -g root -m 0600 config.example.json /etc/gwe-fan-service.json
install -o root -g root -m 0644 gwe-fan-service.service /etc/systemd/system/gwe-fan-service.service
systemctl daemon-reload
installation_done=1
printf '%s\n' 'Installed but not started or enabled. Configuration contains invalid placeholders.'
