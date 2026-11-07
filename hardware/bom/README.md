# Bill of materials

Roughly **$450 to $600** in parts. A working reference, not a locked sourcing list; prices drift and exact SKUs still need pinning. A `bom.csv` should follow.

| Part | Qty | Notes | ~Cost |
|---|---|---|---|
| Jetson Orin Nano Super Dev Kit | 1 | 8 GB. Orin NX also works. | $250 |
| IMX477 camera module (CSI) | 2 | See Cameras below. | $50-70 ea |
| Wide lens | 2 | Matched pair for the module's mount (M12 ~2.7 mm, or C/CS). Field-covering FOV, low distortion. | $15-30 ea |
| Storage (microSD or NVMe) | 1 | A V30 microSD covers 1080p output + a light stacked view; NVMe for heavier use. 256 GB+. | $25-40 |
| USB-C PD power bank | 1 | 25,000 mAh (90 Wh) covers multiple games; a full tournament in testing, and stays under the 100 Wh airline carry-on limit. | $40-70 |
| CSI ribbon cables | 2 | Long enough to reach both cameras. | $5-10 ea |
| 3D-printed case (PETG-CF/ASA) | 1 | STL parts in [`../case/`](../case/). | $10-20 |
| Pole / tripod mount + adapter | 1 | Sideline height. | $20-40 |
| Fasteners + heatset inserts | set | Per the case. | $5-10 |

## Cameras

Two IMX477 modules are in use:

- ([**Arducam IMX477**](https://www.arducam.com/arducam-12-3mp-imx477-camera-module-w-c-cs-lens-mount-and-tripod-adapter-for-raspberry-pi.html)) - CSI module, runs on the Jetson directly. SKU: B0240E
- ([**Raspberry Pi HQ Camera (IMX477)**](https://www.raspberrypi.com/products/raspberry-pi-high-quality-camera/) - needs the **R8 mod** to run on the Jetson ([how-to video](https://www.youtube.com/watch?v=keZFSgiU-Hk)). SKU: CE06935

Use the **same module and lens on both sides** so the stereo pair matches. IMX477 is what the [driver](../../driver/) and calibration are tested against; the calibration path itself is sensor-agnostic. For tighter frame alignment, IMX477 sensors can be hardware-synced through their XVS test points.

## TODO

- [ ] Pin exact SKUs + links; add `bom.csv`.
