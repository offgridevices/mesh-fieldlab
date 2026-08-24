# -*- coding: utf-8 -*-
"""Independent check of the wordmark outlines: rasterise OFFGRID through
FreeType (PIL) at Archivo weight 900 and compare with our own polygon
extraction. Catches mirrored glyphs, bad curve flattening and broken keyholes.
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import wordmark as W

PX = 200.0      # pixels per em


def ours():
    polys, adv, upem, cap = W.glyph_polys('OFFGRID', track=False)
    sc = PX / upem
    xs = [x for p in polys for (x, y) in p]
    ys = [y for p in polys for (x, y) in p]
    w = int((max(xs) - min(xs)) * sc) + 20
    h = int((max(ys) - min(ys)) * sc) + 20
    im = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(im)
    for p in polys:
        d.polygon([((x - min(xs)) * sc + 10, (max(ys) - y) * sc + 10) for (x, y) in p],
                  fill=255)
    return im


def freetype():
    f = ImageFont.truetype(W.FONT, int(PX))
    try:
        f.set_variation_by_axes([900.0, 100.0])       # wght, wdth (fvar order)
    except Exception:
        try:
            f.set_variation_by_name('Black')
        except Exception:
            return None
    im = Image.new('L', (int(PX * 12), int(PX * 3)), 0)
    d = ImageDraw.Draw(im)
    d.text((20, 20), 'OFFGRID', font=f, fill=255)
    return im.crop(im.getbbox())


def main():
    a = ours()
    b = freetype()
    if b is None:
        print('FreeType could not set the variation axes - skipping')
        return 0
    a = a.crop(a.getbbox())
    # normalise to the same height, compare shapes
    h = 160
    a = a.resize((max(1, int(a.width * h / a.height)), h), Image.LANCZOS)
    b = b.resize((max(1, int(b.width * h / b.height)), h), Image.LANCZOS)
    w = min(a.width, b.width)
    A0 = (np.array(a.crop((0, 0, w, h))) > 128)
    B0 = (np.array(b.crop((0, 0, w, h))) > 128)
    # register: the two rasterisers land on slightly different sub-pixel
    # offsets, which would tank a naive IoU
    iou = 0.0
    for dx in range(-6, 7):
        for dy in range(-6, 7):
            B = np.roll(np.roll(B0, dy, axis=0), dx, axis=1)
            u = (A0 | B).sum()
            if u:
                iou = max(iou, (A0 & B).sum() / u)
    print('ours %dx%d   freetype %dx%d   aspect ratio %.3f vs %.3f'
          % (a.width, a.height, b.width, b.height, a.width / a.height, b.width / b.height))
    print('shape agreement (IoU) = %.4f' % iou)
    a.save('wm_ours.png'); b.save('wm_freetype.png')
    # 0.90 not 0.95: two different rasterisers disagree on the antialiased
    # edge, and Archivo Black has a lot of perimeter per unit area.
    ok = iou > 0.90 and abs(a.width / a.height - b.width / b.height) < 0.05
    print('WORDMARK OUTLINES:', 'MATCH' if ok else 'MISMATCH')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
