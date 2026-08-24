# -*- coding: utf-8 -*-
"""Remove any part of a silkscreen LINE that lands on a pad or a hole.
Imported at the end of design.py so the clip is always applied."""
import math


def clip(pads, holes, silk):
    ob = []
    for p in pads:
        m = 0.22
        if p['shape'] == 'rect':
            ob.append(('r', p['x']-p['w']/2-m, p['y']-p['h']/2-m,
                            p['x']+p['w']/2+m, p['y']+p['h']/2+m))
        elif p['shape'] == 'oval':
            w, h = p['w'], p['h']
            r = min(w, h)/2 + m
            if h >= w:
                ob.append(('s', p['x'], p['y']-(h-w)/2, p['x'], p['y']+(h-w)/2, r))
            else:
                ob.append(('s', p['x']-(w-h)/2, p['y'], p['x']+(w-h)/2, p['y'], r))
        else:
            ob.append(('c', p['x'], p['y'], max(p['w'], p['h'])/2 + m))
    for (hx, hy, hd) in holes:
        ob.append(('c', hx, hy, hd/2 + 0.30))

    def hit(px, py, hw):
        for o in ob:
            if o[0] == 'c':
                if (px-o[1])**2 + (py-o[2])**2 <= (o[3]+hw)**2:
                    return True
            elif o[0] == 'r':
                if o[1]-hw <= px <= o[3]+hw and o[2]-hw <= py <= o[4]+hw:
                    return True
            else:
                ax, ay, bx, by, r = o[1], o[2], o[3], o[4], o[5]
                dx, dy = bx-ax, by-ay
                L2 = dx*dx + dy*dy
                t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((px-ax)*dx + (py-ay)*dy)/L2))
                if (px-(ax+t*dx))**2 + (py-(ay+t*dy))**2 <= (r+hw)**2:
                    return True
        return False

    out = []
    for it in silk:
        if it[0] != 'line':
            out.append(it)
            continue
        _, x1, y1, x2, y2, w, layer = it
        L = math.hypot(x2-x1, y2-y1)
        n = max(2, int(L/0.04) + 1)
        bad = [hit(x1+(x2-x1)*k/n, y1+(y2-y1)*k/n, w/2) for k in range(n+1)]
        k = 0
        while k <= n:
            if bad[k]:
                k += 1
                continue
            k0 = k
            while k <= n and not bad[k]:
                k += 1
            k1 = k - 1
            if k1 > k0 and (k1-k0)/n*L > 0.25:
                t0, t1 = k0/n, k1/n
                out.append(('line', x1+(x2-x1)*t0, y1+(y2-y1)*t0,
                                    x1+(x2-x1)*t1, y1+(y2-y1)*t1, w, layer))
    return out
