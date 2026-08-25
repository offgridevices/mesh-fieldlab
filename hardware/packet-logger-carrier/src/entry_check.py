# -*- coding: utf-8 -*-
"""For named pads: where does the trace actually meet the pad, from which
direction, and how much of the trace's width lands on pad copper."""
# routed.pkl is our own build output.
import pickle, math, sys
import design as D


def main(want):
    d = pickle.load(open('routed.pkl', 'rb'))
    tracks = d['tracks']
    for ref, pin in want:
        p = [q for q in D.pads if q['ref'] == ref and q['pin'] == pin][0]
        px, py, net = p['x'], p['y'], p['net']
        if p['shape'] == 'oval':
            hw, hh = p['w'] / 2, p['h'] / 2
            desc = 'oval %.1fx%.1f' % (p['w'], p['h'])
        elif p['shape'] == 'rect':
            hw, hh = p['w'] / 2, p['h'] / 2
            desc = 'square %.1f' % p['w']
        else:
            hw = hh = max(p['w'], p['h']) / 2
            desc = 'round %.1f' % (2 * hw)
        print('%s.%s  net %-9s  %s  centre (%.2f,%.2f)' % (ref, pin, net, desc, px, py))
        for (n, l, x0, y0, x1, y1, w) in tracks:
            if n != net:
                continue
            for (ex, ey), (ox, oy) in (((x0, y0), (x1, y1)), ((x1, y1), (x0, y0))):
                if math.hypot(ex - px, ey - py) > max(hw, hh) + 0.05:
                    continue
                dx, dy = ox - ex, oy - ey
                L = math.hypot(dx, dy) or 1.0
                ang = math.degrees(math.atan2(dy, dx))
                dirn = ('east' if abs(ang) < 45 else 'north' if 45 <= ang < 135
                        else 'west' if abs(ang) >= 135 else 'south')
                # how far can the trace run inside the pad before leaving it?
                run = 0.0
                for t in [i * 0.01 for i in range(400)]:
                    qx, qy = ex + dx / L * t, ey + dy / L * t
                    inside = (abs(qx - px) <= hw and abs(qy - py) <= hh) if p['shape'] != 'circle' \
                        else (math.hypot(qx - px, qy - py) <= hw)
                    if not inside:
                        break
                    run = t
                print('    trace w=%.2f on %-6s ends at (%.2f,%.2f) = %.2f mm from centre, '
                      'heads %s, overlaps pad for %.2f mm'
                      % (w, 'TOP' if l == 0 else 'BOTTOM', ex, ey,
                         math.hypot(ex - px, ey - py), dirn, run))
        print()


if __name__ == '__main__':
    main([('J3','5'),('J3','1')])
