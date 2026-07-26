#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Lens-calibration capture for Gyroflow.
#
# Records the checkerboard at the camera's NATIVE square-pixel mode
# (4032x3040, sensor-mode 0), all-intra, high bitrate, low fps -> every
# frame is a sharp, independent still. This is the footage that makes
# Gyroflow return fy/fx ~= 1.0 (rescaled/16:9 exports give the wrong ~1.10).
#
# Usage:  ./record_lens_calib.sh [seconds] [sensor-id]
#   seconds    recording length (default 45)
#   sensor-id  0 (default) or 1  -- same lens model, calibrate either one
#
# While it records, move the checkerboard through ~15-20 poses: fill the
# frame EDGES and especially the CORNERS (that's where distortion lives),
# tilt it to several angles, keep it flat/rigid and in focus. Ctrl-C to stop early.

set -u
DUR=${1:-45}
SENSOR=${2:-0}
FPS=2                                   # frames/sec kept (deliberate poses; plenty for Gyroflow)
TS=$(date +%Y%m%d_%H%M%S)
OUT="$HOME/calibration/lens_calib_s${SENSOR}_${TS}.mp4"
NBUF=$((DUR * 30))                      # source runs at 30fps

mkdir -p "$HOME/calibration"

# Cameras are single-consumer (nvargus). Don't fight a live recording.
if pgrep -f "reco camera" >/dev/null 2>&1; then
  echo "ERROR: reco is recording. Stop the running capture first (nvargus is single-consumer)."
  exit 1
fi
pkill -x gst-launch-1.0 2>/dev/null; sleep 1
sudo -n systemctl restart nvargus-daemon 2>/dev/null; sleep 3   # clear stale sensor state (NOPASSWD)

echo "Recording ${DUR}s from sensor ${SENSOR} @ 4032x3040, ${FPS}fps all-intra -> $OUT"
echo ">>> Move the checkerboard through poses now (corners + edges + tilts). Ctrl-C to stop early. <<<"

gst-launch-1.0 -e \
  nvarguscamerasrc sensor-id="${SENSOR}" sensor-mode=0 num-buffers="${NBUF}" ! \
  "video/x-raw(memory:NVMM),width=4032,height=3040,framerate=30/1" ! \
  nvvidconv ! videorate ! "video/x-raw,format=I420,framerate=${FPS}/1" ! \
  x264enc speed-preset=ultrafast bitrate=100000 key-int-max=1 ! \
  h264parse ! mp4mux ! filesink location="$OUT"

echo ""
echo "Saved: $OUT"
ls -lh "$OUT" 2>/dev/null
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,r_frame_rate,nb_frames \
  -of default=noprint_wrappers=1 "$OUT" 2>/dev/null
echo "Next: pull this file to your machine and run it through Gyroflow lens calibration."
