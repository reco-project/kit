# Device-tree overlay (IMX477 dual, 4K30)

The kernel module alone is not enough. NVIDIA's Argus stack reads the allowed sensor modes from the device tree, and the stock IMX477 tree does not declare 4032x3040@30. This overlay adds it (plus 2K and 1080p modes). The module and the overlay are a matched pair; without the overlay Argus rejects the mode with `INVALID_SETTINGS`.

## Files

- `tegra234-p3767-camera-p3768-imx477-dual.dtbo` - the compiled overlay.
- `tegra234-p3767-camera-p3768-imx477-dual.dts` - its decompiled source, for reading. It declares the 4032x3040 mode (`active_w=4032, line_length=9024, pix_clk_hz=840000000, max_framerate=30000000`).
- `apply.sh` / `revert.sh` - install / back out.

This is the stock IMX477 dual-camera overlay with the 4K30 mode patched in.

## Apply

```
sudo ./apply.sh        # copies the .dtbo to /boot and adds a boot entry that loads it (default)
sudo reboot
# verify (expect a 4032 x 3040 line):
gst-launch-1.0 nvarguscamerasrc sensor-id=0 num-buffers=1 ! fakesink 2>&1 | grep -A20 'Available Sensor modes'
```

`apply.sh` edits `/boot/extlinux/extlinux.conf` (keeping a backup) to add a boot entry that loads the overlay and makes it the default; the stock `primary` entry stays as a boot-menu fallback. `revert.sh` switches the default back.

NVIDIA's `jetson-io` tool (Configure for compatible hardware -> CSI Camera IMX477 Dual) applies the *stock* overlay; you can run it first, then `apply.sh` swaps in this patched one.

> Exported from a working board (L4T 36.5), not re-validated from a clean flash. Review `apply.sh` first, and keep the `primary` boot entry as your safety net.
