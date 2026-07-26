# Contributing to Reco Kit

A working reference design, not a finished product. It films full matches, but the build takes effort and the path is not yet smooth. Calibration accuracy is being improved by the maintainer; the items below are where outside help goes furthest.

## Most useful contributions

- **A simpler rig.** Make the 3D case easier to build, print, and assemble.
- **A better sensor.** The IMX477 is a compromise (noisy in low light). A cleaner sensor choice, with driver + calibration to match, would help a lot.
- **A better lens.** The current lens choice is a compromise too.
- **Audio.** There is no microphone / audio path yet.
- **Sensor porting.** Adapt the driver + calibration to another CSI sensor.
- **Docs.** Clearer build/flash/calibration guides, troubleshooting, photos.

Calibration accuracy is largely the maintainer's to improve, so it is lower-value as an unsolicited PR unless coordinated. The rig already works; the useful mechanical contribution is a simpler, faster-to-build design (above), not fine polish. A USB-C power bank is the intentional default; other battery setups are possible but unexplored and low priority.

## Before you open a PR

- Match the license of the area you touch (see [`docs/licensing.md`](docs/licensing.md)): hardware CERN-OHL-W-2.0, tooling Apache-2.0, docs CC-BY-SA-4.0, driver GPL-2.0-only (cannot be relicensed).
- Never commit footage, calibration frames, secrets, or private hostnames/keys. Scripts take host/user as arguments; keep them generic.
- Keep the driver's NVIDIA + RidgeRun copyright and GPL-2.0 header intact.

## The engine is separate

The stitch/track/record engine is [video-stitcher](https://github.com/reco-project/video-stitcher); a record/stream app (gameday) is coming. This repo is the hardware, driver, and tooling. Engine changes go there.
