#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Undo apply.sh: boot without the IMX477 overlay, back to the stock kernel entry.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run with sudo:  sudo $0"; exit 1; }

EXT="/boot/extlinux/extlinux.conf"
[ -f "$EXT" ] || { echo "ERROR: $EXT not found"; exit 1; }

cp -f "$EXT" "$EXT.bak.$(date +%Y%m%d_%H%M%S)"
sed -i 's/^DEFAULT .*/DEFAULT primary/' "$EXT"
echo "[overlay] default boot set back to 'primary'. Reboot to boot without the overlay."
echo "The overlay boot entry and the .dtbo in /boot are left in place; delete them by hand if you want them gone."
