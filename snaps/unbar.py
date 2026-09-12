import sys, cv2, numpy as np
def unbar(src, dst):
    img = cv2.imread(src).astype(np.float32)
    H, W = img.shape[:2]
    lum = img.mean(axis=2)
    rows = np.median(lum, axis=1)          # median per row: text pixels ignored
    bh = int(round(0.0883 * W))
    g = np.diff(rows)                      # g[y] = rows[y+1]-rows[y]
    best, y0, y1 = -1e9, None, None
    for a in range(int(H*0.25), int(H*0.9)):
        if g[a-1] > -8: continue           # need a sharp drop entering the bar at row a
        for b in range(a+int(bh*0.8), min(a+int(bh*1.2), H-8)):
            if g[b-1] < 8: continue        # sharp rise leaving the bar at row b
            # column consistency: the darkening must be uniform across the width
            outside = (lum[a-4:a-1].mean(0) + lum[b+1:b+4].mean(0))/2
            inside = (lum[a+1:a+4].mean(0) + lum[b-4:b-1].mean(0))/2
            ratio = inside/np.maximum(outside, 8)
            good = (outside > 25)
            if good.sum() < W*0.3: continue
            score = -g[a-1] + g[b-1] - 60*np.std(ratio[good])
            if score > best: best, y0, y1 = score, a, b
    assert y0 is not None, "no bar found"
    band = img[y0:y1]
    # alpha per channel from boundary rows
    inside = np.concatenate([img[y0:y0+3], img[y1-3:y1]]).reshape(-1,3).mean(0)
    outside = np.concatenate([img[y0-4:y0-1], img[y1+1:y1+4]]).reshape(-1,3).mean(0)
    a = np.clip(1 - inside/np.maximum(outside,1), 0.4, 0.8)
    rec = np.clip(band / (1 - a), 0, 255)
    # text mask: bright, low-saturation pixels in the band
    hsv = cv2.cvtColor(band.astype(np.uint8), cv2.COLOR_BGR2HSV)
    mask = ((hsv[...,2] > 150) & (hsv[...,1] < 60)).astype(np.uint8)*255
    mask = cv2.dilate(mask, np.ones((5,5),np.uint8), iterations=2)
    out = img.copy(); out[y0:y1] = rec
    out = out.astype(np.uint8)
    full = np.zeros((H,W),np.uint8); full[y0:y1] = mask
    out = cv2.inpaint(out, full, 7, cv2.INPAINT_TELEA)
    # soften the band a little to hide amplified noise and the seams
    band_out = cv2.GaussianBlur(out[y0-2:y1+2], (0,0), 1.2)
    out[y0-2:y1+2] = band_out
    cv2.imwrite(dst, out, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(dst, "bar rows", y0, y1, "alpha", a.round(2))
for s in sys.argv[1:]:
    unbar(s, s.rsplit('/',1)[-1].rsplit('.',1)[0] + '-nobar.jpg')
