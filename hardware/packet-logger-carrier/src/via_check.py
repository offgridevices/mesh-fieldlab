# -*- coding: utf-8 -*-
"""Is there a soldermask opening over each via, or are they tented?"""
import numpy as np
import gerber_read as GR
import design as D
# routed.pkl is our own build output, not external input.
import pickle

RES = 0.02
d = pickle.load(open('routed.pkl', 'rb'))
mask = GR.parse('out/gerbers/packet-logger-carrier-F_Mask.gbr', D.BW, D.BH, RES)

for (n, x, y) in d['vias']:
    i = int(round(x / RES)); j = int(round(y / RES))
    r = int(round((D.VIA_D / 2) / RES))
    win = mask[max(0, j - r):j + r + 1, max(0, i - r):i + r + 1]
    open_frac = win.mean() if win.size else 0.0
    print('via %-9s at (%6.2f,%6.2f)  mask opening over it: %s'
          % (n, x, y, 'YES %.0f%%' % (100 * open_frac) if open_frac > 0.05 else 'no (tented)'))
