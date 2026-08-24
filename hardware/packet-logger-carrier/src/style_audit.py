# -*- coding: utf-8 -*-
"""Audit the two things the reviewer raised:
   1. how close do traces actually pass to pads they are NOT connected to
   2. do traces meet their own pad at the centre, or clip in at an angle/edge
"""
# routed.pkl is our own build output.
import pickle, math
import design as D
import drc


def main():
    d = pickle.load(open('routed.pkl', 'rb'))
    tracks, vias = d['tracks'], d['vias']

    # ---- 1. trace vs FOREIGN pad clearance -------------------------------
    gaps = []
    for i, (n, l, x0, y0, x1, y1, w) in enumerate(tracks):
        t = drc.Obj(n, (l,), [((x0, y0), (x1, y1))], w / 2, None, 'trk%d' % i)
        for p in D.pads:
            if p['net'] == n and p['net'] is not None:
                continue
            po = drc.pad_obj(p)
            g = drc.gap(t, po)
            if g < 3.0:
                gaps.append((g, '%s.%s' % (p['ref'], p['pin']), n))
    gaps.sort()
    print('TRACE -> FOREIGN PAD clearance   (design rule 0.25, fab minimum 0.127)')
    print('  tightest 10:')
    for g, pad, net in gaps[:10]:
        print('     %.3f mm   %-8s vs net %s' % (g, pad, net))
    import collections
    b = collections.Counter()
    for g, _, _ in gaps:
        b['0.25-0.30' if g < 0.30 else
          '0.30-0.40' if g < 0.40 else
          '0.40-0.60' if g < 0.60 else
          '0.60+'] += 1
    print('  distribution:', dict(b))

    # ---- 2. does each trace end land on its pad's CENTRE? -----------------
    print()
    print('TRACE -> OWN PAD entry point (0.00 = dead centre)')
    offs = []
    for (n, l, x0, y0, x1, y1, w) in tracks:
        for (ex, ey) in ((x0, y0), (x1, y1)):
            # only count endpoints that actually TERMINATE on a pad: no other
            # track of the same net continues from that point
            cont = sum(1 for (m, l2, a, b, c, e, w2) in tracks
                       if m == n and ((abs(a-ex) < 1e-6 and abs(b-ey) < 1e-6) or
                                      (abs(c-ex) < 1e-6 and abs(e-ey) < 1e-6)))
            if cont > 1:
                continue
            best = None
            for p in D.pads:
                if p['net'] != n:
                    continue
                r = max(p['w'], p['h'])/2
                dd = math.hypot(p['x'] - ex, p['y'] - ey)
                if dd <= r + 0.05 and (best is None or dd < best[0]):
                    best = (dd, '%s.%s' % (p['ref'], p['pin']))
            if best:
                offs.append(best)
    offs.sort(reverse=True)
    print('  worst 10 off-centre entries:')
    for dd, pad in offs[:10]:
        print('     %.3f mm off centre   %s' % (dd, pad))
    n_off = sum(1 for dd, _ in offs if dd > 0.15)
    print('  %d of %d pad entries are more than 0.15 mm off centre' % (n_off, len(offs)))

    # ---- 3. traces threading BETWEEN two adjacent pads --------------------
    print()
    thread = 0
    for (n, l, x0, y0, x1, y1, w) in tracks:
        for p in D.pads:
            for q in D.pads:
                if p is q or p['net'] == n or q['net'] == n:
                    continue
                dpq = math.hypot(p['x'] - q['x'], p['y'] - q['y'])
                if dpq > 2.8:
                    continue
                mx, my = (p['x'] + q['x']) / 2, (p['y'] + q['y']) / 2
                t = drc.Obj(n, (l,), [((x0, y0), (x1, y1))], w / 2, None, 't')
                if drc.pt_seg((mx, my), (x0, y0), (x1, y1)) < 0.45:
                    thread += 1
                    break
            else:
                continue
            break
    print('traces threading between two adjacent foreign pads:', thread)


if __name__ == '__main__':
    main()
