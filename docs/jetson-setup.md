# Jetson setup - from a blank board to working 4K cameras

This gets a Jetson Orin Nano Super from a fresh flash to two IMX477 cameras streaming 4032x3040 at 30 fps through Argus. It stops at "the cameras work and you can preview them." Building the stitch/track/record engine is covered in [video-stitcher](https://github.com/reco-project/video-stitcher); this repo is the hardware and the driver.

Tested on: Jetson Orin Nano Super, **L4T 36.5.0 (JetPack 6.2.2)**, kernel 5.15.x-tegra. Orin NX works the same way.

> **Quick path:** after flashing (section 1), `sudo provisioning/setup.sh` runs the driver build + install, the device-tree overlay, and the performance mode (sections 2-3) in one command. The sections below are the detail behind that script.

## 1. Flash the board

Flash JetPack 6.2.2 (L4T 36.5.0) with NVIDIA SDK Manager, or write the SD-card image. Boot, complete first-run setup, and confirm the release:

```
cat /etc/nv_tegra_release      # expect "R36 (release), REVISION: 4.x"
uname -r                        # 5.15.x-tegra
```

You do not need to rebuild the kernel. The IMX477 4K30 driver ships as an out-of-tree module against the stock kernel, so the board stays boot-safe.

## 2. Install the IMX477 4K30 driver + device-tree overlay (the important part)

NVIDIA's stock `nv_imx477` driver does not expose the 4032x3040 Argus mode (near-full-sensor: the array is 4056x3040). This repo's [`driver/`](../driver/) does. It must be installed as a **matched pair** - the kernel module *and* a device-tree overlay that declares the 4032x3040 sensor mode. The bare `.ko` alone will make Argus fail with `INVALID_SETTINGS`.

1. **Build + install the module** - see [`driver/README.md`](../driver/README.md). It compiles against your running kernel headers and installs to `/usr/lib/modules/$(uname -r)/updates/`. Keep a backup of the stock module first (the README shows how), then `sudo depmod -a`.

2. **Apply the device-tree overlay** that adds the 4032x3040 mode. The overlay is applied through the extlinux boot config (an `OVERLAYS` line, or a patched base DTB). The scripts are in [`driver/dtbo_patches/`](../driver/dtbo_patches/) (`apply.sh` / `revert.sh`).

3. **Reboot**, then confirm the mode is live:

```
sudo systemctl restart nvargus-daemon
gst-launch-1.0 nvarguscamerasrc sensor-id=0 num-buffers=1 ! fakesink 2>&1 | grep -A20 'Available Sensor modes'
# expect a "4032 x 3040" entry at 30 fps
```

If you see `INVALID_SETTINGS`, the module and the overlay are out of sync - the module was installed but the overlay's mode table does not match, or vice versa. They are a pair; re-check both.

## 3. Performance mode

The capture + stitch pipeline wants full clocks. Set the max power profile and lock clocks:

```
sudo nvpmodel -m 2          # MAXN_SUPER on Orin Nano Super
sudo jetson_clocks
```

Make it persistent with a small systemd unit (`RemainAfterExit=yes`) so it survives reboots. MAXN_SUPER holds the clocks up for capture and encode.

## 4. Preview + verify the cameras

Preview tooling is in [`provisioning/`](../provisioning/):

- `preview.py` - a low-latency live preview with a sharpness overlay, for framing and setting focus on the M12 lenses. Point it at the board with `--host <hostname-or-ip>` (default `reco-jetson`; Tailscale, mDNS, or LAN) and set `RECO_SSH_USER` if the SSH user differs.
- `reset_sensor.sh` - restarts `nvargus-daemon` to release a stuck sensor.

The cameras run through Argus (`nvarguscamerasrc`); there is no custom V4L2 path to set up.

## 5. Calibrate + run

Once both cameras preview cleanly and are focused, calibrate the stereo rig ([`calibration/`](../calibration/)) to produce a `match.json`, then build and run the engine ([video-stitcher](https://github.com/reco-project/video-stitcher)) against it.

## Gotchas (ranked)

1. **The driver and the overlay are a matched pair.** The `.ko` alone breaks Argus. Install both, `depmod`, reboot.
2. **The teardown SIGABRT is cosmetic.** On L4T 36.5 the Argus client can throw a `malloc` abort *at teardown* after a clean capture. Recordings finalize fine; do not reflash chasing it.
3. **A stuck sensor after a crash** clears with `sudo systemctl restart nvargus-daemon` (or `reset_sensor.sh`), not a reboot.
4. **Keep the stock kernel.** The driver is out-of-tree on purpose so a bad build never bricks boot; the stock module backup lets you revert instantly.
