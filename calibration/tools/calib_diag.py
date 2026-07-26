#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Detect checkerboard on a frame folder, SAVE annotated overlays + a coverage map
+ per-view reproj error, and cache corners for instant future refits.

Built to diagnose a high-RMS / off-center-cx fisheye calibration: the overlays show
whether detections are clean, and the coverage map shows whether corners ever reach
the image edges (if they don't, cx + distortion are unconstrained -> the +100px cx
and the high RMS are both expected).

Usage: calib_diag.py <frame_dir> <COLSxROWS> <yscale> <out_dir>
"""
import sys, os, glob, json, pickle
import numpy as np, cv2

def list_images(d):
    fs = []
    for e in ("*.jpg","*.jpeg","*.png"):
        fs += glob.glob(os.path.join(d, e))
    return sorted(fs)

def detect(images, cols, rows, yscale):
    objp = np.zeros((rows*cols,3), np.float32)
    objp[:,:2] = np.mgrid[0:cols,0:rows].T.reshape(-1,2)
    objp[:,1] *= yscale
    NB,AC,MK = cv2.CALIB_CB_NORMALIZE_IMAGE, cv2.CALIB_CB_ACCURACY, cv2.CALIB_CB_MARKER
    crit = (cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER,40,0.001)
    c2,c4 = cv2.createCLAHE(2.0,(8,8)), cv2.createCLAHE(4.0,(8,8))
    need = cols*rows
    objpts,imgpts,used,size = [],[],[],None
    for f in images:
        img = cv2.imread(f)
        if img is None: continue
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY); size = g.shape[::-1]
        found = None
        for base in (g, c2.apply(g), c4.apply(g)):
            for target in (1400,1800,2200,2600):
                sc = target/max(base.shape)
                gg = cv2.resize(base,(int(base.shape[1]*sc),int(base.shape[0]*sc))) if sc<1 else base
                scale = base.shape[1]/gg.shape[1]
                for flags in (NB|AC|MK, NB|AC):
                    r = cv2.findChessboardCornersSB(gg,(cols,rows),flags=flags)
                    if r[0] and r[1] is not None and len(r[1])==need:
                        found = r[1].reshape(-1,2).astype(np.float32)*scale; break
                if found is not None: break
            if found is not None: break
        if found is None:
            print(f"  miss  {os.path.basename(f)}"); continue
        corners = cv2.cornerSubPix(g, found.reshape(-1,1,2),(11,11),(-1,-1),crit)
        objpts.append(objp.reshape(-1,1,3).copy())
        imgpts.append(corners.reshape(-1,1,2).astype(np.float32))
        used.append(f); print(f"  OK    {os.path.basename(f)}  ({len(corners)} corners)")
    return objpts, imgpts, used, size

def calib(objpts, imgpts, size):
    K=np.zeros((3,3)); D=np.zeros((4,1)); n=len(objpts)
    rv=[np.zeros((1,1,3)) for _ in range(n)]; tv=[np.zeros((1,1,3)) for _ in range(n)]
    flags = cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC|cv2.fisheye.CALIB_FIX_SKEW
    crit=(cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER,100,1e-6)
    return cv2.fisheye.calibrate(objpts,imgpts,size,K,D,rv,tv,flags,crit)

def main():
    fdir, board, ys, out = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
    cols, rows = map(int, board.lower().split("x"))
    os.makedirs(out, exist_ok=True)
    imgs = list_images(fdir)
    print(f"{len(imgs)} frames, board {cols}x{rows}, yscale {ys}")
    objpts, imgpts, used, size = detect(imgs, cols, rows, ys)
    print(f"\ndetected {len(used)}/{len(imgs)}; size={size}")
    pickle.dump({"objpts":objpts,"imgpts":imgpts,"used":used,"size":size,
                 "cols":cols,"rows":rows,"yscale":ys}, open(os.path.join(out,"corners.pkl"),"wb"))
    rms, K, D, rv, tv = calib(objpts, imgpts, size)
    # per-view error
    errs=[]
    for i in range(len(objpts)):
        proj,_ = cv2.fisheye.projectPoints(objpts[i],rv[i],tv[i],K,D)
        errs.append(cv2.norm(imgpts[i],proj.reshape(imgpts[i].shape),cv2.NORM_L2)/np.sqrt(len(proj)))
    order = np.argsort(errs)[::-1]  # worst first
    # annotated overlays (worst-error frames flagged in red)
    for rank,i in enumerate(order):
        img = cv2.imread(used[i])
        cv2.drawChessboardCorners(img,(cols,rows),imgpts[i],True)
        col = (0,0,255) if errs[i]>2.0 else (0,255,0)
        cv2.putText(img,f"err={errs[i]:.2f}px  {os.path.basename(used[i])}",(40,90),
                    cv2.FONT_HERSHEY_SIMPLEX,2.2,col,5)
        small = cv2.resize(img,(1280,965))
        cv2.imwrite(os.path.join(out,f"det_{rank:02d}_err{errs[i]:.1f}_{os.path.basename(used[i])}.jpg"),
                    small,[cv2.IMWRITE_JPEG_QUALITY,88])
    # coverage map: all corners over the image area, colored by per-view error
    cov = np.full((size[1],size[0],3),30,np.uint8)
    cv2.rectangle(cov,(0,0),(size[0]-1,size[1]-1),(80,80,80),6)
    cv2.drawMarker(cov,(size[0]//2,size[1]//2),(0,200,200),cv2.MARKER_CROSS,80,4)  # geometric center
    cv2.drawMarker(cov,(int(K[0,2]),int(K[1,2])),(0,120,255),cv2.MARKER_TILTED_CROSS,80,4)  # cx,cy
    for i in range(len(imgpts)):
        c = (0,0,255) if errs[i]>2.0 else (0,255,0)
        for p in imgpts[i].reshape(-1,2):
            cv2.circle(cov,(int(p[0]),int(p[1])),5,c,-1)
    cv2.putText(cov,f"cyan=center({size[0]//2},{size[1]//2})  orange=cx,cy({int(K[0,2])},{int(K[1,2])})  red=view err>2px",
                (50,80),cv2.FONT_HERSHEY_SIMPLEX,2.0,(255,255,255),5)
    cv2.imwrite(os.path.join(out,"COVERAGE.jpg"),cv2.resize(cov,(1612,1216)),[cv2.IMWRITE_JPEG_QUALITY,90])
    summary={"rms":float(rms),"views":len(used),"size":list(size),
             "fx":float(K[0,0]),"fy":float(K[1,1]),"cx":float(K[0,2]),"cy":float(K[1,2]),
             "cx_off_px":float(K[0,2]-size[0]/2),"cy_off_px":float(K[1,2]-size[1]/2),
             "D":[float(x) for x in D.flatten()],
             "per_view_err_med":float(np.median(errs)),"per_view_err_max":float(np.max(errs))}
    json.dump(summary, open(os.path.join(out,"summary.json"),"w"), indent=2)
    print(f"\nRMS {rms:.3f}  cx_off {summary['cx_off_px']:+.0f}px cy_off {summary['cy_off_px']:+.0f}px")
    print(f"wrote overlays + COVERAGE.jpg + corners.pkl to {out}")

if __name__ == "__main__":
    main()
