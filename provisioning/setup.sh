#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Reco Kit - partial on-device installer for the Jetson.
#
# Run this AFTER flashing the Jetson (JetPack 6 / L4T 36.5). In one go it:
#   - checks the build prerequisites
#   - builds and installs the IMX477 4K30 driver (backing up the stock module)
#   - sets the performance mode and makes it persistent
#   - applies the 4K30 device-tree overlay (via driver/dtbo_patches/apply.sh)
#
# It does NOT flash the board, calibrate, or build the engine. Those stay manual.
# The overlay step edits the boot config (with a backup, and the stock "primary"
# entry as a fallback); read driver/dtbo_patches/apply.sh to see exactly what it does.
#
# Usage:  sudo ./provisioning/setup.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRIVER="$REPO/driver"
KREL="$(uname -r)"
MOD_DST="/lib/modules/$KREL/updates/drivers/media/i2c/nv_imx477.ko"
DTBO_NAME="tegra234-p3767-camera-p3768-imx477-dual.dtbo"

say()  { printf '\n\033[1m[setup] %s\033[0m\n' "$*"; }
warn() { printf '\033[33m[setup] WARN: %s\033[0m\n' "$*"; }
die()  { printf '\033[31m[setup] ERROR: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run with sudo:  sudo $0"
grep -qi tegra /proc/device-tree/compatible 2>/dev/null || warn "this does not look like a Jetson; continuing anyway"

say "1/5  checking build prerequisites"
[ -d "/lib/modules/$KREL/build" ]                || die "kernel headers missing. Install:  apt install nvidia-jetpack"
[ -f /usr/src/nvidia/nvidia-oot/Module.symvers ] || die "nvidia-oot symbols missing. Install:  apt install nvidia-jetpack"

say "2/5  building the IMX477 4K30 driver"
make -C "$DRIVER" clean >/dev/null 2>&1 || true
make -C "$DRIVER"
[ -f "$DRIVER/nv_imx477.ko" ] || die "build produced no nv_imx477.ko"

say "3/5  installing the module"
mkdir -p "$(dirname "$MOD_DST")"
if [ -f "$MOD_DST" ] && [ ! -f "$MOD_DST.stock_bak" ]; then
  cp -f "$MOD_DST" "$MOD_DST.stock_bak"
  echo "      backed up stock module -> $MOD_DST.stock_bak"
fi
cp -f "$DRIVER/nv_imx477.ko" "$MOD_DST"
depmod -a
echo "      installed -> $MOD_DST"

say "4/5  performance mode (MAXN_SUPER + jetson_clocks), persistent"
nvpmodel -m 2 || warn "nvpmodel -m 2 failed (the mode id can differ per board)"
jetson_clocks  || true
cat > /etc/systemd/system/reco-perf.service <<'UNIT'
[Unit]
Description=Reco Kit performance mode (MAXN_SUPER + jetson_clocks)
After=nvpmodel.service
[Service]
Type=oneshot
ExecStart=/usr/sbin/nvpmodel -m 2
ExecStart=/usr/bin/jetson_clocks
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
UNIT
systemctl enable reco-perf.service >/dev/null 2>&1 || warn "could not enable reco-perf.service"
echo "      enabled reco-perf.service (survives reboots)"

say "5/5  device-tree overlay (4K30)"
if grep -q "OVERLAYS .*$DTBO_NAME" /boot/extlinux/extlinux.conf 2>/dev/null; then
  echo "      overlay already applied"
else
  echo "      applying via driver/dtbo_patches/apply.sh"
  "$DRIVER/dtbo_patches/apply.sh"
fi

say "done. Remaining steps (manual):"
echo "  1. reboot:          sudo reboot"
echo "  2. verify the mode: gst-launch-1.0 nvarguscamerasrc sensor-id=0 num-buffers=1 ! fakesink 2>&1 | grep -A20 'Available Sensor modes'   (expect 4032 x 3040)"
echo "  3. preview + focus: python3 provisioning/preview.py --host <this-board>"
echo "  4. calibrate:       calibration/README.md"
echo "  5. run the engine:  https://github.com/reco-project/video-stitcher"
