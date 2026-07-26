#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
Low-latency high-quality live preview from the Jetson camera.

Streams 4032x3040 RG10 raw Bayer at up to 30fps from /dev/video0, uses a
reader thread that drops stale frames to minimise display latency, runs the
full image pipeline on each rendered frame (LSC, bilinear Bayer
demosaic via OpenCV, WB, CCM, chroma NR, sRGB gamma), then downsamples to
fit a preview window.

Because the SSH pipe is bandwidth-limited (~100 MB/s over Tailscale), the
sensor self-throttles below 30fps. 3-6 fps at 12 MP is typical and fine for
focus tuning -- latency stays under ~500 ms thanks to frame dropping.

Sharpness number overlaid top-left, updated each frame.

This is a CONTINUOUS VIDEO preview (not a still capture). It runs at
2-30fps depending on demosaic mode and network speed. Press `s` to grab a
still JPEG, `v` to start recording an MP4 of the processed output.

Keys during live preview:
  === exit / pause / save ===
    ESC / q        exit
    p              pause/unpause the processing (network stream keeps running)
    s              save current frame to captures/ as JPEG
    v              start/stop recording an MP4 to captures/

  === camera selection + view ===
    c              switch between cam0 and cam1
    r              rotate 90 degrees clockwise (cycles 0/90/180/270)
    f              toggle full-res Malvar demosaic vs fast 2x2 binning

  === sensor-side capture controls (change the actual shutter/gain) ===
    + / =          exposure *= 1.25 (brighter capture)
    -              exposure /= 1.25 (darker capture)
    h              gain += 8 (higher analog gain, more noise)
    g              gain -= 8 (lower, min 16 = cleanest)

  === tonemap + colour (pure software, no sensor change) ===
    .              tonemap white *= 1.15 (dimmer output)
    ,              tonemap white /= 1.15 (brighter output)
    1 / 2          WB red gain -/+ 0.05
    3 / 4          WB blue gain -/+ 0.05
    5 / 6          gamma -/+ 0.1     (default ~2.0, higher = more contrast in shadows)
    7 / 8          saturation -/+ 0.1 (default 1.0, chroma multiplier)
    9 / 0          contrast -/+ 0.1   (default 1.0, multiplies Y around 0.5)

Usage (remote, from your laptop):
    preview.py --host reco-jetson [--cam 0] [--exposure 1500] [--gain 16] [--rotate 90]

Usage (local, on the Jetson with HDMI):
    python3 preview.py --local [--cam 0] [--exposure 1500] [--gain 16] [--rotate 90]
"""
import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter

WIDTH, HEIGHT = 4032, 3040
FRAME_BYTES = WIDTH * HEIGHT * 2

# Daylight-ish WB; tweak with --wb-r / --wb-b if walls look tinted
DEFAULT_WB_R = 1.6
DEFAULT_WB_B = 1.8

# CCM matching our indoor-verified recipe; fine under daylight too
CCM = np.array([
    [1.6, -0.5, -0.1],
    [-0.15, 1.4, -0.25],
    [-0.1, -0.35, 1.45],
], dtype=np.float32)

# Radial lens-shading-correction coefficient
LSC_COEFF = 0.3

# Preview window size (fits on most laptop screens without scrolling)
PREVIEW_W, PREVIEW_H = 1344, 1008


STREAM_REMOTE_PATH = "/tmp/jetson_v4l2_stream.py"


def deploy_stream_helper(host: str, user: str) -> None:
    """Copy the FIFO-based V4L2 streamer to the Jetson once per session."""
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "jetson_v4l2_stream.py")
    subprocess.run(["scp", "-q", local, f"{user}@{host}:{STREAM_REMOTE_PATH}"],
                   check=False)


def remote_cmd(cam: int, exposure: int, gain: int, throttle_fps: float) -> str:
    return (
        f"python3 {STREAM_REMOTE_PATH} --cam {cam} "
        f"--width {WIDTH} --height {HEIGHT} "
        f"--exposure {exposure} --gain {gain} --fps {throttle_fps}"
    )


class LatestFrameReader(threading.Thread):
    """Keep only the newest complete frame; older ones are overwritten."""
    def __init__(self, proc: subprocess.Popen):
        super().__init__(daemon=True)
        self.proc = proc
        self.latest: bytes | None = None
        self.frames_read = 0
        self.stop_flag = threading.Event()

    def run(self) -> None:
        stdout = self.proc.stdout
        assert stdout is not None
        while not self.stop_flag.is_set():
            buf = bytearray()
            while len(buf) < FRAME_BYTES:
                chunk = stdout.read(FRAME_BYTES - len(buf))
                if not chunk:
                    return
                buf.extend(chunk)
            self.latest = bytes(buf)
            self.frames_read += 1


# Precompute the radial LSC map once -- identical per frame.
_lsc_cache: np.ndarray | None = None


def lsc_map() -> np.ndarray:
    global _lsc_cache
    if _lsc_cache is None:
        yy, xx = np.mgrid[0:HEIGHT, 0:WIDTH].astype(np.float32)
        r = np.sqrt(((xx - WIDTH / 2) / (WIDTH / 2)) ** 2 +
                    ((yy - HEIGHT / 2) / (HEIGHT / 2)) ** 2)
        _lsc_cache = 1.0 + LSC_COEFF * r ** 2
    return _lsc_cache


# Malvar-Cutler-He 5x5 demosaic kernels (full-resolution, proven correct on IMX477)
_K_G   = np.array([[0,0,-1,0,0],[0,0,2,0,0],[-1,2,4,2,-1],[0,0,2,0,0],[0,0,-1,0,0]], dtype=np.float32) / 8.0
_K_RG1 = np.array([[0,0,0.5,0,0],[0,-1,0,-1,0],[-1,4,5,4,-1],[0,-1,0,-1,0],[0,0,0.5,0,0]], dtype=np.float32) / 8.0
_K_RG2 = _K_RG1.T
_K_RB  = np.array([[0,0,-1.5,0,0],[0,2,0,2,0],[-1.5,0,6,0,-1.5],[0,2,0,2,0],[0,0,-1.5,0,0]], dtype=np.float32) / 8.0

# Bayer position masks (computed once at module import - faster than per-frame)
_mR  = np.zeros((HEIGHT, WIDTH), dtype=np.float32); _mR[0::2, 0::2] = 1
_mGr = np.zeros((HEIGHT, WIDTH), dtype=np.float32); _mGr[0::2, 1::2] = 1
_mGb = np.zeros((HEIGHT, WIDTH), dtype=np.float32); _mGb[1::2, 0::2] = 1
_mB  = np.zeros((HEIGHT, WIDTH), dtype=np.float32); _mB[1::2, 1::2] = 1


class LocalFrameReader(threading.Thread):
    """Capture raw Bayer frames directly from V4L2 on the Jetson.
    Same interface as LatestFrameReader so the display loop is identical."""
    def __init__(self, cam: int, exposure: int, gain: int, throttle_fps: float):
        super().__init__(daemon=True)
        self.cam = cam
        self.latest: bytes | None = None
        self.frames_read = 0
        self.stop_flag = threading.Event()
        self._fifo_path = f"/tmp/v4l2_raw_fifo_{cam}"
        self._interval = 1.0 / throttle_fps
        self._v4l2_proc: subprocess.Popen | None = None
        self._setup_sensor(exposure, gain)

    def _setup_sensor(self, exposure: int, gain: int) -> None:
        dev = f"/dev/video{self.cam}"
        subprocess.run(
            f"v4l2-ctl -d {dev} "
            f"--set-fmt-video=width={WIDTH},height={HEIGHT},pixelformat=RG10 "
            f"--set-ctrl=bypass_mode=0,override_enable=1,sensor_mode=0,"
            f"frame_rate=30000000,exposure={exposure},gain={gain}",
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    def run(self) -> None:
        try:
            os.unlink(self._fifo_path)
        except FileNotFoundError:
            pass
        os.mkfifo(self._fifo_path)

        dev = f"/dev/video{self.cam}"
        self._v4l2_proc = subprocess.Popen(
            f"exec v4l2-ctl -d {dev} --stream-mmap=4 --stream-to={self._fifo_path}",
            shell=True, stderr=subprocess.DEVNULL, preexec_fn=os.setsid
        )

        last_emit = 0.0
        try:
            with open(self._fifo_path, 'rb') as fifo:
                while not self.stop_flag.is_set():
                    data = b''
                    while len(data) < FRAME_BYTES:
                        chunk = fifo.read(FRAME_BYTES - len(data))
                        if not chunk:
                            return
                        data += chunk
                    now = time.monotonic()
                    if now - last_emit >= self._interval:
                        self.latest = data
                        self.frames_read += 1
                        last_emit = now
        except (KeyboardInterrupt, BrokenPipeError):
            pass
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        if self._v4l2_proc:
            try:
                os.killpg(self._v4l2_proc.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
        try:
            os.unlink(self._fifo_path)
        except FileNotFoundError:
            pass

    def terminate(self) -> None:
        self.stop_flag.set()
        self._cleanup()


class PipelineState:
    """Live-tunable ISP parameters. Single object so keyboard handlers + the
    frame processor share state cleanly."""
    def __init__(self, wb_r: float, wb_b: float, white: float):
        self.wb_r = wb_r
        self.wb_b = wb_b
        self.white = white
        self.gamma = 2.0         # higher = darker midtones, punchier shadows
        self.saturation = 1.0    # chroma multiplier in YCbCr
        self.contrast = 1.0      # luma scale around 0.5


def process_frame(raw: np.ndarray, st: PipelineState, fast: bool = False) -> np.ndarray:
    """
    raw: HxW uint16 (10-bit in upper bits).
    Returns BGR uint8 at true sensor resolution (4032x3040) using the full
    Malvar-Cutler-He demosaic we verified yesterday. cv2.filter2D does the
    heavy lifting in C so full-frame 4K takes ~150-300ms on a desktop CPU.

    If fast=True, falls back to 2x2 binning (half-res, ~10x faster).
    """
    f = (raw >> 6).astype(np.float32) - 64.0
    np.maximum(f, 0, out=f)
    f *= lsc_map()

    if fast:
        R = f[0::2, 0::2].copy()
        Gr = f[0::2, 1::2]
        Gb = f[1::2, 0::2]
        B = f[1::2, 1::2].copy()
        G = 0.5 * (Gr + Gb)
    else:
        G_interp = cv2.filter2D(f, -1, _K_G, borderType=cv2.BORDER_REPLICATE)
        R_g1 = cv2.filter2D(f, -1, _K_RG1, borderType=cv2.BORDER_REPLICATE)
        R_g2 = cv2.filter2D(f, -1, _K_RG2, borderType=cv2.BORDER_REPLICATE)
        R_b  = cv2.filter2D(f, -1, _K_RB,  borderType=cv2.BORDER_REPLICATE)
        G = f * (_mGr + _mGb) + G_interp * (_mR + _mB)
        R = f * _mR + R_g1 * _mGr + R_g2 * _mGb + R_b * _mB
        B = f * _mB + R_g1 * _mGb + R_g2 * _mGr + R_b * _mR

    R *= st.wb_r
    B *= st.wb_b

    stack = np.stack([R, G, B], axis=-1)
    ccm = stack @ CCM.T

    Y = 0.299 * ccm[..., 0] + 0.587 * ccm[..., 1] + 0.114 * ccm[..., 2]
    Cb = -0.169 * ccm[..., 0] - 0.331 * ccm[..., 1] + 0.500 * ccm[..., 2]
    Cr = 0.500 * ccm[..., 0] - 0.419 * ccm[..., 1] - 0.081 * ccm[..., 2]
    Cb = gaussian_filter(Cb, sigma=2.0)
    Cr = gaussian_filter(Cr, sigma=2.0)
    # Saturation: scale chroma directly (1.0 = neutral)
    Cb *= st.saturation
    Cr *= st.saturation
    R2 = Y + 1.402 * Cr
    G2 = Y - 0.344 * Cb - 0.714 * Cr
    B2 = Y + 1.772 * Cb

    inv_g = 1.0 / max(st.gamma, 0.1)

    def tm(ch):
        x = np.clip(ch / st.white, 0, 1)
        # Apply contrast as a scaling around mid-grey (post-normalisation)
        x = (x - 0.5) * st.contrast + 0.5
        x = np.clip(x, 0, 1)
        # Variable gamma (2.0 ~ sqrt; 2.2 ~ sRGB; higher = punchier shadows)
        return (np.power(x, inv_g) * 255).astype(np.uint8)

    return np.stack([tm(B2), tm(G2), tm(R2)], axis=-1)


def sharpness_of(raw: np.ndarray) -> float:
    """Laplacian variance on centre green patch (at sensor resolution)."""
    f = (raw >> 6).astype(np.float32)
    cy, cx = HEIGHT // 2, WIDTH // 2
    g = f[cy - 256:cy + 256:2, cx - 256 + 1:cx + 256:2]
    # Apply laplacian via cv2 for speed
    lap = cv2.Laplacian(g, cv2.CV_32F, ksize=1)
    return float(lap.var())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--host", help="Remote Jetson hostname (SSH mode)")
    group.add_argument("--local", action="store_true",
                       help="Run directly on the Jetson with HDMI output")
    parser.add_argument("--user", help="SSH user on the Jetson (default: same as --host)")
    parser.add_argument("--cam", type=int, default=0)
    parser.add_argument("--exposure", type=int, default=1500,
                        help="Microseconds. Daytime outdoors: 500-2000. Indoor: 8000-30000.")
    parser.add_argument("--gain", type=int, default=16,
                        help="Analog gain 16-357. Keep low outdoors (16) for cleanest image.")
    parser.add_argument("--wb-r", type=float, default=DEFAULT_WB_R)
    parser.add_argument("--wb-b", type=float, default=DEFAULT_WB_B)
    parser.add_argument("--white", type=float, default=350.0,
                        help="Tonemap white point (scene-linear units). "
                             "Lower = brighter output. Typical 200-500.")
    parser.add_argument("--rotate", type=int, default=0, choices=[0, 90, 180, 270],
                        help="Initial rotation in degrees (clockwise). Can be toggled live with 'r'.")
    parser.add_argument("--captures-dir", default="captures",
                        help="Where 's' key saves JPEGs (default ./captures/).")
    parser.add_argument("--throttle-fps", type=float, default=2.0,
                        help="Frames per second sent over SSH (Jetson drops "
                             "the rest). Default 2 fps -- full raw quality but "
                             "network-friendly. Raise for more responsive focus.")
    args = parser.parse_args()

    is_local = args.local
    user = args.user or (args.host if args.host else None)
    captures_dir = os.path.abspath(args.captures_dir)
    os.makedirs(captures_dir, exist_ok=True)

    cur_cam = args.cam
    cur_exposure = args.exposure
    cur_gain = args.gain

    if is_local:
        print(f"starting LOCAL preview /dev/video{args.cam} (4032x3040)", file=sys.stderr)
    else:
        deploy_stream_helper(args.host, user)
        print(f"starting preview from {args.host} /dev/video{args.cam} (4032x3040)", file=sys.stderr)
    print(f"  exposure={args.exposure}us gain={args.gain} wb=R*{args.wb_r}/B*{args.wb_b} white={args.white}", file=sys.stderr)
    print("  see module docstring or press any unused key for the key reference", file=sys.stderr)

    def start_capture_remote(cam: int) -> tuple[subprocess.Popen | None, LatestFrameReader | LocalFrameReader]:
        ssh_cmd = ["ssh", f"{user}@{args.host}",
                   remote_cmd(cam, cur_exposure, cur_gain, args.throttle_fps)]
        p = subprocess.Popen(ssh_cmd, stdout=subprocess.PIPE, bufsize=0)
        r = LatestFrameReader(p)
        r.start()
        return p, r

    def start_capture_local(cam: int) -> tuple[None, LocalFrameReader]:
        r = LocalFrameReader(cam, cur_exposure, cur_gain, args.throttle_fps)
        r.start()
        return None, r

    def start_capture(cam: int):
        if is_local:
            return start_capture_local(cam)
        return start_capture_remote(cam)

    def stop_capture(p, r) -> None:
        if isinstance(r, LocalFrameReader):
            r.terminate()
            return
        r.stop_flag.set()
        if p is not None:
            p.terminate()
            try:
                p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                p.kill()
        if not is_local:
            subprocess.run(
                ["ssh", f"{user}@{args.host}",
                 "pkill -9 v4l2-ctl 2>/dev/null; "
                 "pkill -9 -f jetson_v4l2_stream 2>/dev/null; true"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )

    proc, reader = start_capture(cur_cam)

    win = "Reco camera preview"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, PREVIEW_W, PREVIEW_H)
    host_label = "local" if is_local else args.host
    cv2.setWindowTitle(win, f"Reco camera preview - cam{cur_cam} @ {host_label}")

    last_frame_seen = 0
    last_fps_ts = time.time()
    last_fps_frames = 0
    display_fps = 0.0
    peak_sharp = 1.0
    rotation = args.rotate
    rotation_codes = {
        0: None,
        90: cv2.ROTATE_90_CLOCKWISE,
        180: cv2.ROTATE_180,
        270: cv2.ROTATE_90_COUNTERCLOCKWISE,
    }
    last_full_bgr: np.ndarray | None = None  # cached for save-on-keypress
    fast_mode = False  # toggled with 'f' -- trades resolution for latency

    # cur_exposure / cur_gain are already declared above the start_capture
    # closure so cam switches see the current live values.
    state = PipelineState(args.wb_r, args.wb_b, args.white)
    paused = False
    video_writer: cv2.VideoWriter | None = None
    video_path: str | None = None

    def update_sensor_ctrl() -> None:
        """Push exposure+gain to the currently-active cam without stopping the stream."""
        ctrl_cmd = (
            f"v4l2-ctl -d /dev/video{cur_cam} "
            f"--set-ctrl=exposure={cur_exposure},gain={cur_gain}"
        )
        if is_local:
            subprocess.Popen(
                ctrl_cmd, shell=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                ["ssh", f"{user}@{args.host}", ctrl_cmd + " >/dev/null"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )

    try:
        while True:
            if reader.latest is None:
                if cv2.waitKey(30) & 0xFF in (27, ord("q")):
                    break
                continue

            buf = reader.latest
            seen = reader.frames_read
            if seen == last_frame_seen:
                if cv2.waitKey(15) & 0xFF in (27, ord("q")):
                    break
                continue
            dropped = seen - last_frame_seen - 1
            last_frame_seen = seen

            raw = np.frombuffer(buf, dtype=np.uint16).reshape(HEIGHT, WIDTH)
            t0 = time.time()
            sharp = sharpness_of(raw)
            if not paused:
                bgr = process_frame(raw, state, fast=fast_mode)
                last_full_bgr = bgr
            else:
                bgr = last_full_bgr if last_full_bgr is not None else \
                    process_frame(raw, state, fast=True)
            rot_code = rotation_codes[rotation]
            if rot_code is not None:
                bgr = cv2.rotate(bgr, rot_code)
            # Fit rotated frame in the preview window
            target_w, target_h = (PREVIEW_W, PREVIEW_H) if rotation in (0, 180) else (PREVIEW_H, PREVIEW_W)
            preview = cv2.resize(bgr, (target_w, target_h), interpolation=cv2.INTER_AREA)
            t_process = (time.time() - t0) * 1000
            peak_sharp = max(sharp, peak_sharp * 0.995)

            now = time.time()
            if now - last_fps_ts >= 0.5:
                display_fps = (seen - last_fps_frames) / (now - last_fps_ts)
                last_fps_ts = now
                last_fps_frames = seen

            # Write to video file (before overlay so the file is clean)
            if video_writer is not None and not paused:
                # cv2.VideoWriter was opened with the current bgr shape; if
                # the frame shape changes (e.g. fast/full mode toggle), we
                # have to close + reopen the writer.
                vf = bgr
                if rot_code is not None:
                    vf = cv2.rotate(vf, rot_code)
                video_writer.write(vf)

            # Overlay
            mode_label = "fast(1/2)" if fast_mode else "full"
            pause_tag = "  [PAUSED]" if paused else ""
            rec_tag = "  [REC]" if video_writer is not None else ""
            lines = [
                f"cam{cur_cam}  sharp {sharp:>7.0f}   peak {peak_sharp:>7.0f}{pause_tag}{rec_tag}",
                f"fps   {display_fps:>5.1f}   drop {dropped}   proc {t_process:>4.0f}ms   mode {mode_label}",
                f"exp {cur_exposure:>6d}us  gain {cur_gain:>3d}  rot {rotation:3d}",
                f"wb R*{state.wb_r:.2f} B*{state.wb_b:.2f}  white {state.white:.0f}  gamma {state.gamma:.2f}",
                f"sat {state.saturation:.2f}   contrast {state.contrast:.2f}",
                "keys: s=save v=rec p=pause r=rot f=full c=cam  exp+/-  gain g/h  white ,/.  wb 1-4  gamma 5/6  sat 7/8  contrast 9/0",
            ]
            for i, line in enumerate(lines):
                y = 28 + i * 28
                cv2.putText(preview, line, (11, y + 1), cv2.FONT_HERSHEY_SIMPLEX,
                            0.7, (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(preview, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX,
                            0.7, (255, 255, 255), 1, cv2.LINE_AA)

            cv2.imshow(win, preview)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                break
            if key == ord("r"):
                rotation = (rotation + 90) % 360
                print(f"\nrotation -> {rotation}", file=sys.stderr)
            if key == ord("f"):
                fast_mode = not fast_mode
                print(f"\nmode -> {'fast (half-res)' if fast_mode else 'full-res Malvar'}", file=sys.stderr)
            if key in (ord("+"), ord("=")):
                cur_exposure = min(int(cur_exposure * 1.25), 1000000)
                update_sensor_ctrl()
                print(f"\nexposure -> {cur_exposure}us", file=sys.stderr)
            if key == ord("-"):
                cur_exposure = max(int(cur_exposure / 1.25), 10)
                update_sensor_ctrl()
                print(f"\nexposure -> {cur_exposure}us", file=sys.stderr)
            if key == ord("h"):
                cur_gain = min(cur_gain + 8, 357)
                update_sensor_ctrl()
                print(f"\ngain -> {cur_gain}", file=sys.stderr)
            if key == ord("g"):
                cur_gain = max(cur_gain - 8, 16)
                update_sensor_ctrl()
                print(f"\ngain -> {cur_gain}", file=sys.stderr)
            if key == ord("c"):
                new_cam = 1 - cur_cam
                print(f"\nswitching to cam{new_cam}...", file=sys.stderr)
                stop_capture(proc, reader)
                cur_cam = new_cam
                proc, reader = start_capture(cur_cam)
                last_frame_seen = 0
                cv2.setWindowTitle(win, f"Reco camera preview - cam{cur_cam} @ {host_label}")
            if key == ord("."):
                state.white *= 1.15
                print(f"\nwhite -> {state.white:.0f}", file=sys.stderr)
            if key == ord(","):
                state.white = max(state.white / 1.15, 10.0)
                print(f"\nwhite -> {state.white:.0f}", file=sys.stderr)
            if key == ord("1"):
                state.wb_r = max(state.wb_r - 0.05, 0.1); print(f"\nwb_r -> {state.wb_r:.2f}", file=sys.stderr)
            if key == ord("2"):
                state.wb_r = min(state.wb_r + 0.05, 5.0); print(f"\nwb_r -> {state.wb_r:.2f}", file=sys.stderr)
            if key == ord("3"):
                state.wb_b = max(state.wb_b - 0.05, 0.1); print(f"\nwb_b -> {state.wb_b:.2f}", file=sys.stderr)
            if key == ord("4"):
                state.wb_b = min(state.wb_b + 0.05, 5.0); print(f"\nwb_b -> {state.wb_b:.2f}", file=sys.stderr)
            if key == ord("5"):
                state.gamma = max(state.gamma - 0.1, 0.5); print(f"\ngamma -> {state.gamma:.2f}", file=sys.stderr)
            if key == ord("6"):
                state.gamma = min(state.gamma + 0.1, 4.0); print(f"\ngamma -> {state.gamma:.2f}", file=sys.stderr)
            if key == ord("7"):
                state.saturation = max(state.saturation - 0.1, 0.0); print(f"\nsat -> {state.saturation:.2f}", file=sys.stderr)
            if key == ord("8"):
                state.saturation = min(state.saturation + 0.1, 3.0); print(f"\nsat -> {state.saturation:.2f}", file=sys.stderr)
            if key == ord("9"):
                state.contrast = max(state.contrast - 0.1, 0.1); print(f"\ncontrast -> {state.contrast:.2f}", file=sys.stderr)
            if key == ord("0"):
                state.contrast = min(state.contrast + 0.1, 3.0); print(f"\ncontrast -> {state.contrast:.2f}", file=sys.stderr)
            if key == ord("p"):
                paused = not paused
                print(f"\n{'paused' if paused else 'resumed'}", file=sys.stderr)
            if key == ord("v"):
                if video_writer is None:
                    # Start recording. Use the rotated frame shape so the
                    # file matches the on-screen orientation.
                    sample = last_full_bgr if last_full_bgr is not None else bgr
                    if rot_code is not None:
                        sample = cv2.rotate(sample, rot_code)
                    vh, vw = sample.shape[:2]
                    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                    video_path = os.path.join(
                        captures_dir,
                        f"cam{cur_cam}_{ts}_video.mp4",
                    )
                    # mp4v works everywhere; for smaller files swap to avc1 if your cv2 has it.
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    # Target display-fps; actual per-frame write cadence varies.
                    video_writer = cv2.VideoWriter(video_path, fourcc, max(display_fps, 2.0), (vw, vh))
                    print(f"\nrecording -> {video_path}", file=sys.stderr)
                else:
                    video_writer.release()
                    print(f"\nstopped recording: {video_path}", file=sys.stderr)
                    video_writer = None
                    video_path = None
            if key == ord("s") and last_full_bgr is not None:
                save_bgr = last_full_bgr
                if rot_code is not None:
                    save_bgr = cv2.rotate(save_bgr, rot_code)
                ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                path = os.path.join(
                    captures_dir,
                    f"cam{cur_cam}_{ts}_exp{cur_exposure}_g{cur_gain}"
                    f"_wbR{state.wb_r:.2f}B{state.wb_b:.2f}"
                    f"_w{int(state.white)}_gam{state.gamma:.1f}_sat{state.saturation:.1f}_rot{rotation}.jpg",
                )
                cv2.imwrite(path, save_bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
                print(f"\nsaved {path}", file=sys.stderr)
            if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                break
    except KeyboardInterrupt:
        pass
    finally:
        if video_writer is not None:
            video_writer.release()
            print(f"\nclosed video: {video_path}", file=sys.stderr)
        stop_capture(proc, reader)
        cv2.destroyAllWindows()
        print(f"\nread {reader.frames_read} frames on cam{cur_cam}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
