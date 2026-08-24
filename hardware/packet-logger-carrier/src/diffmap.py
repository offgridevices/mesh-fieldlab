# -*- coding: utf-8 -*-
"""Show WHERE our gerbers differ from KiCad's export, so we can judge whether
each difference is benign."""
import numpy as np
import gerber_read as GR
import design as D

K = '/Users/shreyashgupta/.claude/jobs/d1c8fae8/tmp/kigerb/packet-logger-carrier-'
M = 'out/gerbers/packet-logger-carrier-'
RES = 0.05


def dil(m, n=2):
    for _ in range(n):
        r = m.copy()
        r[1:, :] |= m[:-1, :]
        r[:-1, :] |= m[1:, :]
        r[:, 1:] |= m[:, :-1]
        r[:, :-1] |= m[:, 1:]
        m = r
    return m


def clusters(mask, tol=2.0):
    """crude clustering of differing cells into boxes"""
    js, is_ = np.nonzero(mask)
    pts = list(zip(is_ * RES, js * RES))
    boxes = []
    for (x, y) in pts:
        for b in boxes:
            if b[0] - tol <= x <= b[2] + tol and b[1] - tol <= y <= b[3] + tol:
                b[0] = min(b[0], x); b[1] = min(b[1], y)
                b[2] = max(b[2], x); b[3] = max(b[3], y)
                b[4] += 1
                break
        else:
            boxes.append([x, y, x, y, 1])
    return sorted(boxes, key=lambda b: -b[4])


def main(lay):
    a = GR.parse(M + lay + '.gbr', D.BW, D.BH, RES)
    b = GR.parse(K + lay + '.gbr', D.BW, D.BH, RES, ox=-20.0, oy=78.0)
    only_ours = a & ~dil(b)
    only_kicad = b & ~dil(a)
    for name, m in (('only in OURS', only_ours), ('only in KICAD', only_kicad)):
        tot = m.sum() * RES * RES
        print('  %-14s %7.2f mm2' % (name, tot))
        for bx in clusters(m)[:6]:
            print('       box x %5.1f..%5.1f  y %5.1f..%5.1f   %.2f mm2'
                  % (bx[0], bx[2], bx[1], bx[3], bx[4] * RES * RES))


if __name__ == '__main__':
    import sys
    for lay in sys.argv[1:]:
        print('===', lay)
        main(lay)
