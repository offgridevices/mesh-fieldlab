# -*- coding: utf-8 -*-
"""Compare our hand-written Gerbers against KiCad's own export of the same
board. Two independent generators agreeing is a strong correctness signal."""
import numpy as np
import gerber_read as GR
import design as D

K = '/Users/shreyashgupta/.claude/jobs/d1c8fae8/tmp/kigerb/packet-logger-carrier-'
M = 'out/gerbers/packet-logger-carrier-'
RES = 0.05


def dil(m):
    r = m.copy()
    r[1:, :] |= m[:-1, :]
    r[:-1, :] |= m[1:, :]
    r[:, 1:] |= m[:, :-1]
    r[:, :-1] |= m[:, 1:]
    return r


def main():
    for lay in ('F_Cu', 'B_Cu', 'F_Mask', 'B_Mask', 'Edge_Cuts'):
        try:
            a = GR.parse(M + lay + '.gbr', D.BW, D.BH, RES)
        except Exception as e:
            print('%-10s OUR parse error: %s' % (lay, str(e)[:80]))
            continue
        try:
            b = GR.parse(K + lay + '.gbr', D.BW, D.BH, RES, ox=-20.0, oy=78.0)
        except Exception as e:
            print('%-10s KICAD parse error: %s' % (lay, str(e)[:80]))
            continue
        bad = (a & ~dil(dil(b))) | (b & ~dil(dil(a)))
        print('%-10s ours=%8.2f mm2   kicad=%8.2f mm2   real diff=%.3f mm2'
              % (lay, a.sum() * RES * RES, b.sum() * RES * RES,
                 bad.sum() * RES * RES))
        if bad.any():
            js, is_ = np.nonzero(bad)
            print('           first difference near x=%.1f y=%.1f'
                  % (is_[0] * RES, js[0] * RES))


if __name__ == '__main__':
    main()
