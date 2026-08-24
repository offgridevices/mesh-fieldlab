# -*- coding: utf-8 -*-
"""Real Archivo 900 glyph outlines for the OFFGRID wordmark.

The brand ships the lockup as handoff/logo/svg/offgrid-wordmark-horizontal.svg:

    viewBox 0 0 800 200
    mark   : translate(20 12) then the 200x200 beacon mark
    text   : x=240 y=125  Archivo weight 900  size 92  letter-spacing -3

so the geometry below reproduces those ratios exactly rather than eyeballing
the placement. Glyphs are emitted as filled polygons (holes keyholed) so the
Gerber and the KiCad board carry identical artwork.
"""
import math
import os

FONT = os.path.expanduser('~/Library/Fonts/Archivo-VariableFont_wdth,wght.ttf')

# --- lockup constants, straight out of the brand SVG -----------------
MARK_DX, MARK_DY = 20.0, 12.0     # transform on the mark group
TEXT_X, TEXT_Y = 240.0, 125.0     # text anchor in lockup space
TEXT_SIZE = 92.0
TEXT_TRACK = -3.0                 # letter-spacing, lockup units


def _instance():
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
    f = TTFont(FONT)
    f = instancer.instantiateVariableFont(f, {'wght': 900, 'wdth': 100},
                                          inplace=False, updateFontNames=False)
    return f


class _Pen:
    """Collects flattened contours in font units."""

    def __init__(self, steps=10):
        self.contours = []
        self.cur = []
        self.steps = steps
        self._start = (0.0, 0.0)
        self._last = (0.0, 0.0)

    def moveTo(self, p):
        self._flushpt()
        self.cur = [p]
        self._start = p
        self._last = p

    def lineTo(self, p):
        self.cur.append(p)
        self._last = p

    def qCurveTo(self, *pts):
        pts = list(pts)
        on = pts[-1]
        if on is None:                      # all-off-curve TrueType contour
            on = ((pts[0][0] + pts[-2][0]) / 2.0, (pts[0][1] + pts[-2][1]) / 2.0)
            pts[-1] = on
        prev = self._last
        offs = pts[:-1]
        # split consecutive off-curve points with implied on-curve midpoints
        seq = []
        for i, c in enumerate(offs):
            if i + 1 < len(offs):
                mid = ((c[0] + offs[i + 1][0]) / 2.0, (c[1] + offs[i + 1][1]) / 2.0)
                seq.append((c, mid))
            else:
                seq.append((c, on))
        for (c, e) in seq:
            for k in range(1, self.steps + 1):
                t = k / self.steps
                x = (1 - t) ** 2 * prev[0] + 2 * (1 - t) * t * c[0] + t * t * e[0]
                y = (1 - t) ** 2 * prev[1] + 2 * (1 - t) * t * c[1] + t * t * e[1]
                self.cur.append((x, y))
            prev = e
        self._last = on

    def curveTo(self, *pts):
        c1, c2, e = pts[-3], pts[-2], pts[-1]
        p0 = self._last
        for k in range(1, self.steps + 1):
            t = k / self.steps
            m = 1 - t
            x = m**3*p0[0] + 3*m*m*t*c1[0] + 3*m*t*t*c2[0] + t**3*e[0]
            y = m**3*p0[1] + 3*m*m*t*c1[1] + 3*m*t*t*c2[1] + t**3*e[1]
            self.cur.append((x, y))
        self._last = e

    def closePath(self):
        self._flushpt()

    def endPath(self):
        self._flushpt()

    def _flushpt(self):
        if len(self.cur) >= 3:
            self.contours.append(self.cur)
        self.cur = []

    def addComponent(self, name, tr):
        pass


def _area(c):
    s = 0.0
    for i in range(len(c)):
        x0, y0 = c[i]
        x1, y1 = c[(i + 1) % len(c)]
        s += x0 * y1 - x1 * y0
    return s / 2.0


def _keyhole(outer, holes):
    """Splice each hole into the outer contour with a zero-width bridge so the
    result is one simply-connected polygon that fills correctly everywhere."""
    poly = list(outer)
    for h in holes:
        best = None
        for i, p in enumerate(poly):
            for j, q in enumerate(h):
                d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
                if best is None or d < best[0]:
                    best = (d, i, j)
        _, i, j = best
        hh = h[j:] + h[:j + 1]
        poly = poly[:i + 1] + hh + poly[i:]
    return poly


def glyph_polys(text='OFFGRID', track=True):
    """Returns (polys, advance_total) in FONT UNITS, baseline at y=0, x from 0."""
    f = _instance()
    gs = f.getGlyphSet()
    cmap = f.getBestCmap()
    hmtx = f['hmtx']
    upem = f['head'].unitsPerEm
    track_fu = (TEXT_TRACK / TEXT_SIZE * upem) if track else 0.0
    polys = []
    pen_x = 0.0
    for ch in text:
        gname = cmap.get(ord(ch))
        pen = _Pen()
        gs[gname].draw(pen)
        cs = pen.contours
        # Classify by NESTING DEPTH rather than winding: TrueType outer
        # contours run clockwise, so a naive signed-area test picks the
        # counters instead of the letters.
        depth = []
        for i, c in enumerate(cs):
            d = 0
            for j, o in enumerate(cs):
                if i != j and _point_in(c[0], o):
                    d += 1
            depth.append(d)
        for i, c in enumerate(cs):
            if depth[i] % 2:            # odd depth = a hole, handled below
                continue
            mine = []
            for j, h in enumerate(cs):
                if j != i and depth[j] == depth[i] + 1 and _point_in(h[0], c):
                    # run the hole against the outer's winding
                    mine.append(h if _area(h) * _area(c) < 0 else h[::-1])
            p = _keyhole(c, mine) if mine else c
            polys.append([(x + pen_x, y) for (x, y) in p])
        pen_x += hmtx[gname][0] + track_fu
    return polys, pen_x - track_fu, upem, f['OS/2'].sCapHeight


def _point_in(pt, poly):
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            xin = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if x < xin:
                inside = not inside
    return inside


def lockup(cx_mark, cy_mark, mark_height_mm, text='OFFGRID', optical_align=True):
    """Place mark + wordmark using the brand SVG's own ratios.

    cx_mark/cy_mark  : where the MARK's bounding box centre lands, in mm
    mark_height_mm   : height of the mark bbox (ring + node), in mm
    returns (scale_mm_per_lockup_unit, text_polys_mm)
    """
    MARK_H = 153.97                        # mark bbox height in mark units
    s = mark_height_mm / MARK_H            # mm per lockup unit

    polys_fu, adv_fu, upem, cap = glyph_polys(text)
    fs = TEXT_SIZE / upem                  # font units -> lockup units

    # mark bbox in lockup space
    mark_x0 = MARK_DX + 100 - 69.0
    mark_y_top = MARK_DY + 40 - 17.0       # top of the node
    mark_y_bot = MARK_DY + 107.97 + 69.0
    mark_cx = MARK_DX + 100.0
    mark_cy = (mark_y_top + mark_y_bot) / 2.0

    out = []
    for p in polys_fu:
        q = []
        for (fx, fy) in p:
            lx = TEXT_X + fx * fs          # lockup space
            ly = TEXT_Y - fy * fs          # SVG y is down; glyph y is up
            q.append((cx_mark + (lx - mark_cx) * s,
                      cy_mark - (ly - mark_cy) * s))   # board y is up
        out.append(q)

    if optical_align and out:
        # The brand SVG's own baseline (y=125) leaves the wordmark riding about
        # 12% of the mark height high - measurably off centre, and it reads as
        # misaligned at this size. Drop the text so its ink centre sits on the
        # mark's AREA centroid (ring + node), which is the optical centre.
        import math as _m
        ring_cy = cy_mark - 7.985 * s
        node_cy = ring_cy + 67.97 * s
        r_out, r_in, r_node = 69 * s, 47 * s, 17 * s
        a_ring = _m.pi * (r_out**2 - r_in**2)
        a_node = _m.pi * r_node**2
        target = (a_ring * ring_cy + a_node * node_cy) / (a_ring + a_node)
        ys = [y for q in out for (x, y) in q]
        dy = target - (min(ys) + max(ys)) / 2.0
        out = [[(x, y + dy) for (x, y) in q] for q in out]

    width_lockup = (TEXT_X + adv_fu * fs) - mark_x0
    return s, out, width_lockup
