#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Install the reviewed unified candidate, then perform unprivileged grouped acceptance.
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
test "$EUID" -ne 0 || { echo 'Run as the desktop user, without prefixing sudo'; exit 1; }
candidate="$PWD/build/release-rc1/gwe-nvml_1.0.0~rc1_all.deb"
test -f "$candidate" || { echo 'Build and review the release candidate first'; exit 1; }
python=${GWE_INSTALL_PYTHON:-/usr/bin/python3}
"$python" scripts/check_controllers.py
(cd -- "$(dirname -- "$candidate")" && sha256sum --check SHA256SUMS)
# APT simulation must match the reviewed transition; unrelated changes require separate review.
simulation=$(LC_ALL=C apt-get --simulate install "$candidate")
printf '%s\n' "$simulation"
while IFS= read -r line; do
    case "$line" in
        'Inst gwe-nvml ('*|'Conf gwe-nvml ('*|'Remv gwe-nvml-client '*|'Remv gwe-nvml-service '*) ;;
        'Inst '*|'Conf '*|'Remv '*|'Purg '*)
            echo 'Unreviewed package change; stop and review the APT transaction' >&2; exit 1 ;;
    esac
done <<< "$simulation"
# The package's own guards reject active service/recovery records before mutation.
sudo apt-get --yes --no-download install "$candidate"
/usr/bin/python3 scripts/check_installed_session.py --native
echo 'Unified candidate installed and grouped native acceptance passed. Launch with: gwe-nvml'
