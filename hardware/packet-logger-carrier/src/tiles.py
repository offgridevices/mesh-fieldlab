# -*- coding: utf-8 -*-
"""Cut the fab render into overlapping tiles at readable magnification so the
silkscreen can actually be inspected rather than glanced at."""
import numpy as np
from PIL import Image
import gerber_read as GR
import design as D

RES = 0.015
B = 'out/gerbers/packet-logger-carrier-'


def board_image():
    cu = GR.parse(B + 'F_Cu.gbr', D.BW, D.BH, RES)
    mask = GR.parse(B + 'F_Mask.gbr', D.BW, D.BH, RES)
    silk = GR.parse(B + 'F_Silkscreen.gbr', D.BW, D.BH, RES)
    import gerber_render as GRN
    dr = GRN.drills() if False else None
    H, W = cu.shape
    img = np.zeros((H, W, 3), np.uint8)
    img[:, :] = (27, 24, 19)
    img[cu] = (37, 33, 26)
    img[mask & cu] = (205, 170, 100)
    img[mask & ~cu] = (120, 104, 74)
    img[silk] = (241, 236, 224)
    return Image.fromarray(img[::-1])


def main():
    im = board_image()
    W, H = im.size
    px_per_mm = 1.0 / RES
    # 3 columns x 2 rows, with overlap
    cols, rows = 3, 2
    ov = 0.08
    out = []
    for r in range(rows):
        for c in range(cols):
            x0 = max(0, int(W * (c / cols - ov)))
            x1 = min(W, int(W * ((c + 1) / cols + ov)))
            y0 = max(0, int(H * (r / rows - ov)))
            y1 = min(H, int(H * ((r + 1) / rows + ov)))
            t = im.crop((x0, y0, x1, y1))
            sc = min(2.0, 1900.0 / t.width)
            t = t.resize((int(t.width * sc), int(t.height * sc)), Image.LANCZOS)
            fn = 'tile_r%dc%d.png' % (r, c)
            t.save(fn)
            out.append(fn)
            print(fn, t.size,
                  ' covers x %.0f..%.0f  y %.0f..%.0f mm'
                  % (x0 * RES, x1 * RES, D.BH - y1 * RES, D.BH - y0 * RES))
    return out


if __name__ == '__main__':
    main()
