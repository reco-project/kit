# AGENTS.md

Guidance for AI agents (and new contributors) working in this repo.

## What this is

Reco Kit is the **open hardware** for a dual-camera sports capture rig: an NVIDIA Jetson (Orin Nano Super or Orin NX) plus two IMX477 4K cameras in a 3D-printed case. This repo holds the hardware design, the IMX477 kernel driver, Jetson provisioning + calibration tooling, and docs.

It is one of three separate repos. Do not move code between them:
- **kit** (here) - hardware, driver, tooling.
- **video-stitcher** - the stitch/track/record engine (AGPL-3.0). The actual CV/tracking lives there.
- **gameday** (coming, not yet published) - a record/stream web app on top of the engine.

## Layout

```
hardware/     BOM, 3D-printed case, assembly + wiring   (CERN-OHL-W-2.0)
driver/       IMX477 4K30 Jetson kernel driver          (GPL-2.0-only, isolated)
provisioning/ Jetson preview + sensor reset             (Apache-2.0)
calibration/  stereo calibration tools + guide          (Apache-2.0 / CC-BY-SA-4.0)
community/    contributed helper tools                  (Apache-2.0)
docs/         setup, calibration, licensing             (CC-BY-SA-4.0)
```

## Rules

- **License by artifact.** Match the license of the area you touch (see `docs/licensing.md`). Do not apply one license across the repo.
- **The driver is GPL-2.0-only** and derives from the Linux kernel + NVIDIA + RidgeRun. Never relicense it or strip its SPDX header or copyright notices.
- **No secrets, PII, private hosts, customer footage, or calibration frames.** Scripts take host/user as arguments (default host `reco-jetson`, SSH user from `RECO_SSH_USER`); keep them generic. Never hardcode hostnames, IPs, keys, or personal names.
- **Argus only.** The Jetson runs the cameras through Argus (`nvarguscamerasrc`); there is no custom V4L2 path.
- **The Orin Nano has no hardware encoder** (software x264). Orin NX adds NVENC; keep that distinction in mind for any encode-related work.

## Build + verify

- Driver: see `driver/README.md` (out-of-tree module against the running kernel). It needs its device-tree overlay (`driver/dtbo_patches/`) to expose 4032x3040@30.
- Preview a camera: `provisioning/preview.py --host <board>`.

## Style

Honest and understated, matching the README: say what works and what does not. No hype, no em dashes, keep it concise. `STATUS.md` tracks what is not yet included; `CONTRIBUTING.md` covers how to help.
