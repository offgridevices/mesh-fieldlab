# -*- coding: utf-8 -*-
"""Teardrops: flare the trace out where it meets a pad.

Removes the acute trace/pad corner (which can trap etchant), puts more copper
at the joint so it survives drill wander, and is what a hand-tidied board looks
like. Built from real track segments on the same net, so KiCad connectivity and
our own DRC still see them as ordinary copper.
"""
import math


def _pad_reach(p, ux, uy):
    """half-extent of the pad along the unit direction (ux,uy)"""
    if p['shape'] == 'circle':
        return max(p['w'], p['h']) / 2.0
    hw, hh = p['w'] / 2.0, p['h'] / 2.0
    if p['shape'] == 'rect':
        tx = abs(hw / ux) if abs(ux) > 1e-9 else 1e9
        ty = abs(hh / uy) if abs(uy) > 1e-9 else 1e9
        return min(tx, ty)
    # oval / obround: stadium of width min(w,h) along the long axis
    r = min(hw, hh)
    if hh >= hw:
        a = hh - r
        return abs(uy) * a + math.sqrt(max(0.0, r * r - (a * ux) ** 2 * 0)) if False else \
            _stadium_reach(a, r, ux, uy, vertical=True)
    a = hw - r
    return _stadium_reach(a, r, ux, uy, vertical=False)


def _stadium_reach(a, r, ux, uy, vertical):
    """distance from centre to the stadium boundary along (ux,uy)"""
    lo, hi = 0.0, a + r + 1.0
    for _ in range(40):
        m = (lo + hi) / 2.0
        x, y = ux * m, uy * m
        if vertical:
            dy = max(0.0, abs(y) - a)
            d = math.hypot(x, dy)
        else:
            dx = max(0.0, abs(x) - a)
            d = math.hypot(dx, y)
        if d <= r:
            lo = m
        else:
            hi = m
    return lo


def build(tracks, pads, steps=5, extra=0.75, frac=0.88):
    """Returns (teardrop_segments, rebuilt_tracks).

    The underlying trace is split where each teardrop ends, so the teardrop tip
    meets a real vertex instead of landing mid-track - otherwise KiCad reports
    the tip as a dangling end."""
    out = []
    splits = {}
    for (n, l, x0, y0, x1, y1, w) in list(tracks):
        for (ex, ey), (ox, oy) in (((x0, y0), (x1, y1)), ((x1, y1), (x0, y0))):
            hit = None
            for p in pads:
                if p['net'] != n or n is None:
                    continue
                if math.hypot(p['x'] - ex, p['y'] - ey) <= max(p['w'], p['h']) / 2.0 + 0.05:
                    hit = p
                    break
            if hit is None:
                continue
            dx, dy = ox - ex, oy - ey
            L = math.hypot(dx, dy)
            if L < 1e-6:
                continue
            ux, uy = dx / L, dy / L
            # Only flare a segment that actually RUNS THROUGH the pad centre.
            # A segment whose end merely falls inside the pad radius (a corner
            # passing by) would put the teardrop out in space beside the trace.
            perp = abs((hit['x'] - ex) * (-uy) + (hit['y'] - ey) * ux)
            if perp > 0.08:
                continue
            R = _pad_reach(hit, ux, uy)
            wide = min(hit['w'], hit['h']) * frac
            if wide <= w + 0.02:
                continue
            # A teardrop must never run past the end of the segment it sits on -
            # otherwise it carries straight on where the trace turns and lands
            # on whatever is next door.
            cx, cy = hit['x'], hit['y']
            # measure the room from the PAD CENTRE (where the teardrop starts),
            # not from the track endpoint - they are not the same point.
            Lc = math.hypot(ox - cx, oy - cy)
            span = min(R + extra, Lc * 0.85)
            if span <= R * 0.6:
                continue
            key = (n, l, x0, y0, x1, y1, w)
            splits.setdefault(key, []).append((cx + ux * span, cy + uy * span))
            for k in range(steps):
                d0 = span * k / steps
                d1 = span * (k + 1) / steps
                t0 = d0 / span
                t1 = d1 / span
                wk = wide + (w - wide) * ((t0 + t1) / 2.0)
                if wk <= w:
                    continue
                out.append((n, l,
                            cx + ux * d0, cy + uy * d0,
                            cx + ux * d1, cy + uy * d1, round(wk, 3)))

    rebuilt = []
    for seg in tracks:
        pts = splits.get(seg)
        if not pts:
            rebuilt.append(seg)
            continue
        (n, l, x0, y0, x1, y1, w) = seg
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        ts = sorted({0.0, 1.0} |
                    {max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / (L * L)))
                     for (px, py) in pts})
        for k in range(len(ts) - 1):
            a, b = ts[k], ts[k + 1]
            if (b - a) * L < 0.01:
                continue
            rebuilt.append((n, l, x0 + dx * a, y0 + dy * a,
                            x0 + dx * b, y0 + dy * b, w))
    return out, rebuilt
