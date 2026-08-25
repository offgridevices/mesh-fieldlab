# -*- coding: utf-8 -*-
"""Find the largest teardrop that still clears everything."""
import importlib, sys
import design as D
import router as R
import teardrops
import build as B
import drc


def try_frac(f, extra):
    rt = R.Router()
    fails = []
    for n in B.ORDER:
        if n not in {p['net'] for p in D.pads if p['net']}:
            continue
        ok, _ = rt.route_net(n, B.WIDTH.get(n, D.TW_SIG))
        if not ok:
            fails.append(n)
    td = teardrops.build(rt.tracks, D.pads, frac=f, extra=extra)
    tracks = rt.tracks + td
    objs = drc.build_objs(tracks, rt.vias)
    worst = 9e9
    bad = 0
    for i in range(len(objs)):
        a = objs[i]
        for j in range(i + 1, len(objs)):
            b = objs[j]
            if a.net == b.net and a.net is not None:
                continue
            if a.net is None and b.net is None:
                continue
            if not (set(a.layers) & set(b.layers)):
                continue
            g = drc.gap(a, b)
            worst = min(worst, g)
            if g < drc.MIN_CLR - 1e-6:
                bad += 1
    return len(td), worst, bad, fails


if __name__ == '__main__':
    for f, e in ((0.70, 0.75), (0.60, 0.65), (0.52, 0.55), (0.45, 0.50)):
        nt, worst, bad, fails = try_frac(f, e)
        print('frac %.2f extra %.2f -> %3d teardrop segs, worst clearance %.3f mm, '
              '%d violations %s' % (f, e, nt, worst, bad, fails or ''))
