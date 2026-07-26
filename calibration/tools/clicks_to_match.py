#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Turn hand-clicked correspondences into a deployable reco match.json.

Runs reco-calibrate's `optimize_points` solver on the clicked pairs, then
assembles a match.json using the given lens profile + rig tilt.

Usage:
  clicks_to_match.py <clicks.json> <lens_profile.json> <out_match.json> [rig_tilt_deg=19]

The clicks.json must already be in optimizer/plane format (from the hand-click capture tool).
"""
import json, subprocess, sys, math, re, os

def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)

def num(text, name):
    """Parse `name: <float>` from optimizer output. Returns None if absent so
    the caller can fail loudly instead of silently substituting 0.0 (which
    produced clean-looking but garbage all-zeros match.json files)."""
    m = re.search(re.escape(name) + r":\s*([-0-9.eE]+)", text)
    return float(m.group(1)) if m else None

def main():
    if len(sys.argv) < 4:
        print(__doc__); sys.exit(1)
    clicks, lens_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
    rig_deg = float(sys.argv[4]) if len(sys.argv) > 4 else 19.0

    for p in (clicks, lens_path):
        if not os.path.exists(p):
            die(f"input not found: {p}")

    binp = os.path.expanduser(
        "~/Documents/dev/reco/video-stitcher/target/release/examples/optimize_points")
    if not os.path.exists(binp):
        die(f"optimizer binary not found: {binp}\n"
            "build it: cargo build --release -p reco-calibrate --example optimize_points")

    r = subprocess.run([binp, clicks], capture_output=True, text=True)
    err = r.stderr + r.stdout  # the result block goes to stderr; be defensive
    if r.returncode != 0:
        die(f"optimizer exited {r.returncode}:\n{err.strip()[-800:]}")

    want = ["cameraAxisOffset", "intersect", "xTy", "xRz", "zRx", "zRz"]
    parsed = {k: num(err, k) for k in want}
    missing = [k for k, v in parsed.items() if v is None]
    if missing:
        die(f"optimizer output missing fields {missing} (run failed/changed format):\n"
            f"{err.strip()[-800:]}")

    residual = num(err, "residual")
    # All-zeros is the classic silent-failure signature; refuse to write it.
    if all(abs(parsed[k]) < 1e-9 for k in ("cameraAxisOffset", "intersect")):
        die("optimizer returned all-zero geometry (intersect=axisOffset=0) -- "
            "almost certainly a failed solve; refusing to write a dead match.json.\n"
            f"{err.strip()[-800:]}")

    params = dict(parsed); params["xRx"] = 0.0
    print(f"optimizer: intersect={params['intersect']:.4f} "
          f"axisOffset={params['cameraAxisOffset']:.4f} "
          f"residual={residual if residual is not None else float('nan'):.6f}")

    lp = json.load(open(lens_path))
    fe = lp["fisheye_params"]; cm = fe["camera_matrix"]; cd = lp["calib_dimension"]
    uni = {"width": cd["w"], "height": cd["h"],
           "fx": cm[0][0], "fy": cm[1][1], "cx": cm[0][2], "cy": cm[1][2],
           "d": fe["distortion_coeffs"]}
    match = {
        "left_uniforms": uni,
        "right_uniforms": dict(uni),
        "params": params,
        "rig_tilt": math.radians(rig_deg),
        "rig_roll": 0.0,
        "sync_offset": 0,
        "field_roi": {"left": [], "right": []},
    }
    json.dump(match, open(out, "w"), indent=2)
    print(f"wrote {out} (rig_tilt {rig_deg} deg)")

if __name__ == "__main__":
    main()
