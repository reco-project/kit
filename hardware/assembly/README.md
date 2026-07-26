# Assembly + wiring

How the parts go together, from bare board to a mounted, cabled unit.

## To be added

- [ ] Exploded view / assembly order (board, cameras, case halves, fasteners).
- [ ] CSI cable routing (straightforward) and strain relief.
- [ ] Power wiring - USB-C PD input, any internal distribution.
- [ ] Photos of each step and the finished unit.
- [ ] Mounting to a pole / tripod.

> Photos and the step-by-step are not in the repo yet. This folder is a placeholder; capture them during a real build.

## What matters

- **Camera orientation and side.** Which physical camera is `sensor-id=0` (left) vs `sensor-id=1` (right) is currently trial-and-error, not yet deterministic, so confirm with `provisioning/preview.py` before closing the case; a wrong assignment mirrors the stitch.
- **Rigid geometry.** The two cameras must hold their fixed relative position; the calibration assumes it does not move. Anything that lets a camera shift will drift the seam.
- **Focus before closing.** Set both M12 lenses with `provisioning/preview.py` (it shows a live sharpness number) while you can still reach them. Then wrap the lens threads with PTFE plumber's tape so focus holds and the lens does not drift over time.
