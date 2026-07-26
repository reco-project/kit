#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Install the patched IMX477 dual-camera device-tree overlay (adds 4032x3040@30,
# plus 2K and 1080p modes) and make the board boot with it.
#
# It copies the overlay into /boot and adds a boot entry that loads it, set as
# the default. The stock "primary" boot entry is left intact as a fallback you
# can pick from the boot menu (extlinux TIMEOUT) if anything is wrong.
#
# Run AFTER installing the driver, then reboot. This overlay was exported from a
# working board (L4T 36.5); it has NOT been re-validated from a clean flash, so
# review this script first and verify the mode after reboot (command at the end).
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run with sudo:  sudo $0"; exit 1; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="tegra234-p3767-camera-p3768-imx477-dual.dtbo"
SRC="$HERE/$NAME"
DST="/boot/$NAME"
EXT="/boot/extlinux/extlinux.conf"

[ -f "$SRC" ] || { echo "ERROR: $SRC not found"; exit 1; }
[ -f "$EXT" ] || { echo "ERROR: $EXT not found (not an extlinux Jetson?)"; exit 1; }

echo "[overlay] installing $NAME -> /boot"
cp -f "$SRC" "$DST"

BK="$EXT.bak.$(date +%Y%m%d_%H%M%S)"
cp -f "$EXT" "$BK"
echo "[overlay] backed up extlinux -> $BK"

if grep -q "OVERLAYS .*$NAME" "$EXT"; then
  echo "[overlay] a boot entry already loads this overlay; extlinux left as-is"
else
  # Optional base DTB that jetson-io generates. OVERLAYS also works on the
  # default DTB, so this is best-effort.
  FDT_DTB="$(ls /boot/dtb/kernel_*nv-super.dtb 2>/dev/null | head -1 || true)"
  # Reuse the primary entry's kernel command line so root=, console=, etc. match.
  APPEND_LINE="$(awk '/^LABEL primary/{f=1} f&&/APPEND/{sub(/^[[:space:]]+/,"\t"); print; exit}' "$EXT")"
  [ -n "$APPEND_LINE" ] || APPEND_LINE=$'\tAPPEND ${cbootargs}'
  echo "[overlay] adding a boot entry that loads the overlay"
  {
    echo ""
    echo "LABEL JetsonIO"
    echo $'\tMENU LABEL Reco Kit: IMX477 Dual (4K30)'
    echo $'\tLINUX /boot/Image'
    [ -n "$FDT_DTB" ] && echo $'\tFDT '"$FDT_DTB"
    echo $'\tINITRD /boot/initrd'
    echo "$APPEND_LINE"
    echo $'\tOVERLAYS /boot/'"$NAME"
  } >> "$EXT"
fi

# Boot it by default.
if grep -q '^DEFAULT ' "$EXT"; then
  sed -i 's/^DEFAULT .*/DEFAULT JetsonIO/' "$EXT"
else
  sed -i '1i DEFAULT JetsonIO' "$EXT"
fi

echo "[overlay] done. Reboot, then verify:"
echo "  gst-launch-1.0 nvarguscamerasrc sensor-id=0 num-buffers=1 ! fakesink 2>&1 | grep -A20 'Available Sensor modes'   (expect 4032 x 3040)"
echo "  If the board misbehaves, pick 'primary kernel' at the boot menu and run revert.sh."
