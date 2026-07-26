#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""KB4 fisheye calibration v2 - precision-first.

Pipeline:
  pass 1 (fast): downscale-1400 SB to find which frames have a board (skip walking)
  pass 2 (precise): on board frames, SB at FULL-RES (then 3400/2800 fallback),
                    trust radon subpixel (NO cornerSubPix), geometric validity
  calibrate with iterative drop, save lens profile + overlays + coverage + cache.

Usage: calib_v2.py <frame_dir> <COLSxROWS> <yscale> <out_dir> [drop=1.5]
"""
import sys, os, glob, json, pickle, numpy as np, cv2

def main():
    fdir, board, ys, out = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
    drop = float(sys.argv[5]) if len(sys.argv) > 5 else 1.5
    COLS, ROWS = map(int, board.lower().split("x")); NEED = COLS*ROWS
    os.makedirs(out, exist_ok=True)
    clahe = cv2.createCLAHE(2.0, (8, 8))
    SB  = cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_ACCURACY
    SBM = SB | cv2.CALIB_CB_MARKER

    def sb(g, fl):
        r = cv2.findChessboardCornersSB(g, (COLS, ROWS), flags=fl)
        return r[1].reshape(-1,2).astype(np.float32) if (r[0] and r[1] is not None and len(r[1])==NEED) else None

    def valid(c):
        g = c.reshape(ROWS, COLS, 2)
        dh = np.diff(g,axis=1).reshape(-1,2); dv = np.diff(g,axis=0).reshape(-1,2)
        lh = np.linalg.norm(dh,axis=1); lv = np.linalg.norm(dv,axis=1)
        if lh.min() < 0.25*np.median(lh) or lv.min() < 0.25*np.median(lv): return False
        mh, mv = dh.mean(0), dv.mean(0)
        if np.any(dh@mh < 0) or np.any(dv@mv < 0): return False
        return True

    def quick_has_board(g):
        s = max(g.shape)/1400.0
        gg = cv2.resize(g,(int(g.shape[1]/s),int(g.shape[0]/s)))
        for src in (clahe.apply(gg), gg):
            for fl in (SBM, SB):
                if sb(src, fl) is not None: return True
        return False

    def precise(g):
        gc = clahe.apply(g)
        for t in (None, 3400, 2800, 2200):   # full-res first, then mild downscale
            if t is None: srcs = [(gc,1.0),(g,1.0)]
            else:
                s = max(g.shape)/t
                srcs = [(cv2.resize(x,(int(g.shape[1]/s),int(g.shape[0]/s))), s) for x in (gc,g)]
            for src, sc in srcs:
                for fl in (SBM, SB):
                    c = sb(src, fl)
                    if c is not None:
                        c = c*sc
                        if valid(c): return c   # trust radon subpix, NO cornerSubPix
        return None

    objp = np.zeros((NEED,3),np.float32); objp[:,:2] = np.mgrid[0:COLS,0:ROWS].T.reshape(-1,2); objp[:,1]*=ys
    imgs = sorted(glob.glob(os.path.join(fdir,"*.jpg")))
    print(f"{len(imgs)} frames, board {COLS}x{ROWS}, yscale {ys}, drop {drop}")
    ipts, used, size = [], [], None
    for f in imgs:
        img = cv2.imread(f)
        if img is None: continue
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY); size = g.shape[::-1]
        if not quick_has_board(g):
            print(f"  skip  {os.path.basename(f)}"); continue
        c = precise(g)
        if c is None:
            print(f"  miss  {os.path.basename(f)}  (board seen, precise detect failed)"); continue
        ipts.append(c); used.append(f); print(f"  OK    {os.path.basename(f)}")
    print(f"\ndetected {len(used)}/{len(imgs)}")

    def cal(ix):
        op=[objp.reshape(-1,1,3).copy() for _ in ix]; ip=[ipts[j].reshape(-1,1,2).astype(np.float32) for j in ix]
        K=np.zeros((3,3));D=np.zeros((4,1));n=len(ix);rv=[np.zeros((1,1,3)) for _ in range(n)];tv=[np.zeros((1,1,3)) for _ in range(n)]
        rms,K,D,rv,tv=cv2.fisheye.calibrate(op,ip,size,K,D,rv,tv,cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC|cv2.fisheye.CALIB_FIX_SKEW,(cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER,100,1e-6))
        e=np.array([cv2.norm(ip[i],cv2.fisheye.projectPoints(op[i],rv[i],tv[i],K,D)[0].reshape(ip[i].shape),cv2.NORM_L2)/np.sqrt(NEED) for i in range(n)])
        return rms,K,D,e

    keep=list(range(len(ipts)))
    rms,K,D,e=cal(keep)
    print(f"no-drop: {len(keep)} views RMS {rms:.3f}")
    for _ in range(6):
        rms,K,D,e=cal(keep); med=np.median(e)
        nk=[keep[j] for j in range(len(keep)) if e[j]<=drop*med]
        if len(nk)==len(keep) or len(nk)<8: break
        keep=nk
    rms,K,D,e=cal(keep)
    pickle.dump({"ipts":[ipts[j] for j in keep],"used":[used[j] for j in keep],"size":size,
                 "all_ipts":ipts,"all_used":used,"objp":objp},open(os.path.join(out,"corners.pkl"),"wb"))
    print(f"\n=== RESULT: {len(keep)} views  RMS {rms:.3f}  cx_off {K[0,2]-size[0]/2:+.1f}  cy_off {K[1,2]-size[1]/2:+.1f}  fy/fx {K[1,1]/K[0,0]:.4f}")
    print(f"D = {[round(float(x),5) for x in D.flatten()]}")
    summary={"rms":float(rms),"views":len(keep),"detected":len(used),"size":list(size),
             "fx":float(K[0,0]),"fy":float(K[1,1]),"cx":float(K[0,2]),"cy":float(K[1,2]),
             "cx_off":float(K[0,2]-size[0]/2),"cy_off":float(K[1,2]-size[1]/2),
             "D":[float(x) for x in D.flatten()]}
    json.dump(summary,open(os.path.join(out,"summary.json"),"w"),indent=2)
    print(f"wrote {out}/summary.json + corners.pkl")

if __name__ == "__main__":
    main()
