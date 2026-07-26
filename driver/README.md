# imx477 - patched NVIDIA tegracam driver

Out-of-tree build of NVIDIA's `nv_imx477` (L4T 36.4.3 tegracam), patched to add the **4032x3040 @ 30fps** mode (4:3, 10-bit Bayer; near-full-sensor, the array is 4056x3040) for the Jetson Orin Nano on L4T R36.5 / JetPack 6. The stock driver does not expose this mode; the patch follows RidgeRun's reference.

Built against `/usr/src/nvidia/nvidia-oot/Module.symvers` so the module resolves `tegracam_device_register` and friends correctly.

## Files

- `nv_imx477.c` - upstream NVIDIA L4T 36.4.3 driver (with a small `conftest.h` stub so it compiles against L4T 36.5 headers).
- `imx477_mode_tbls.h` - patched mode tables. Adds 4032x3040@30 (sensor_mode=0) and 2028x1520@60 (sensor_mode=3, currently VI-rejected). See the history backups:
  - `.before0x0820` - pre CSI link-rate fix
  - `.withbadfrm` - had the 4-lane duplicate frmfmt row that shifted all mode indices (fixed by removing that row).
  - `.pre_2k60` - last known good before the 2K60 experiment.
- `Makefile` - builds out-of-tree against nvidia-oot symbols.
- `nvidia/conftest.h` - one-line stub that defines `NV_I2C_DRIVER_STRUCT_REMOVE_RETURN_TYPE_INT 1` so the driver compiles on 36.5's kernel headers.

## Build + install

On the Jetson:

```bash
cd ~/imx477_build
make
sudo cp nv_imx477.ko /lib/modules/$(uname -r)/updates/drivers/media/i2c/nv_imx477.ko
sudo depmod -a
sudo reboot
```

## Device tree

This driver requires a matching device-tree overlay at
`/boot/tegra234-p3767-camera-p3768-imx477-dual.dtbo` with
`line_length=9024, pix_clk_hz=840000000, max_framerate=30000000` on mode0.
Install it with the scripts in `../dtbo_patches/` (`sudo ./apply.sh`).

## Argus (the normal path)

Normal use goes through Argus, not raw V4L2. The overlay in [`dtbo_patches/`](dtbo_patches/) declares the sensor to NVIDIA's camera stack (`tegra-camera-platform` + per-mode descriptors) and this driver binds to it via `compatible = "ridgerun,imx477"`, so `nvarguscamerasrc` sees the 4K mode.

```bash
# confirm Argus enumerates the 4032x3040 mode
gst-launch-1.0 nvarguscamerasrc sensor-id=0 num-buffers=1 ! fakesink 2>&1 | grep -A20 'Available Sensor modes'

# capture 4032x3040 @ 30fps through Argus (zero-copy NVMM)
gst-launch-1.0 nvarguscamerasrc sensor-id=0 ! \
  'video/x-raw(memory:NVMM),width=4032,height=3040,framerate=30/1' ! \
  nvvidconv ! fakesink
```

## Raw sensor check (V4L2, ISP-bypassed)

A register-level sanity check that the sensor streams; not the normal path.

```bash
# 4032x3040 @ 30fps (main mode; use --stream-to=/dev/null to avoid USB rootfs bottleneck)
v4l2-ctl -d /dev/video0 --set-fmt-video=width=4032,height=3040,pixelformat=RG10
v4l2-ctl -d /dev/video0 --set-ctrl=bypass_mode=0,override_enable=1,sensor_mode=0,frame_rate=30000000,exposure=20000,gain=50
v4l2-ctl -d /dev/video0 --stream-mmap=4 --stream-count=N --stream-to=<sink>
```

`bypass_mode=0` and `override_enable=1` are required -- without them, the driver ignores user exposure/gain ctrl values.

## Upstream references

- NVIDIA L4T 36.4.3 tegracam: https://github.com/woosy/nvgpu-jetson-linux-36.4.3/blob/main/nvidia-oot/drivers/media/i2c/nv_imx477.c
- Sony IMX477 datasheet: https://www.sony-semicon.com/files/62/pdf/p-13_IMX477-AACK_Flyer.pdf
- RidgeRun Nano patch (working 4032@30 reference): https://github.com/RidgeRun/NVIDIA-Jetson-IMX477-RPIV3/
