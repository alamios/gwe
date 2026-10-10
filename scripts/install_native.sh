#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Run as the desktop user from a terminal; sudo is used only for package migration.
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
test "$EUID" -ne 0 || { echo 'Run as your desktop user, without prefixing sudo'; exit 1; }
python=${GWE_INSTALL_PYTHON:-/usr/bin/python3}
"$python" scripts/check_controllers.py
state="${XDG_DATA_HOME:-$HOME/.local/share}/gwe-nvml/state"
mkdir -p -- "$state"
exec 9>"$state/control-session.lock"
flock -n 9 || { echo 'Close the running GWE session first'; exit 1; }
sudo /usr/bin/python3 -I scripts/install_native.py
GWE_STATE_HOME="$state/native-smoke" /usr/bin/python3 \
    /usr/share/gwe-nvml/scripts/run_service_gui.py --demo --smoke-startup
echo 'Native installation and simulated GTK check passed. Launch with: gwe-nvml'
