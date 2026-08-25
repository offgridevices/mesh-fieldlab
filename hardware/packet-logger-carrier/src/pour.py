# -*- coding: utf-8 -*-
"""Ground fill for BOTH layers, with thermal reliefs, sliver removal, island
handling and stitching vias tying the two planes together."""
import math
import numpy as np
import design as D

GR       = 0.05
POUR_CLR = 0.35      # generated clearance (design rule is 0.30)
EDGE_CU  = 0.35
TGAP     = 0.35      # thermal gap
SPOKE    = 0.65      # thermal spoke width
MIN_W    = 0.30      # remove copper slivers thinner than this
MIN_ISL  = 3.0       # mm^2 - drop orphan islands smaller than this
STITCH_R = D.VIA_D / 2 + 0.10

NX = int(round(D.BW/GR))+1
NY = int(round(D.BH/GR))+1


def _disc(m,x,y,r,val=True):
    i0,i1=max(0,int((x-r)/GR)),min(NX-1,int(math.ceil((x+r)/GR)))
    j0,j1=max(0,int((y-r)/GR)),min(NY-1,int(math.ceil((y+r)/GR)))
    if i1<i0 or j1<j0: return
    ii=np.arange(i0,i1+1)*GR-x; jj=np.arange(j0,j1+1)*GR-y
    sel=(jj[:,None]**2+ii[None,:]**2<=r*r)
    sub=m[j0:j1+1,i0:i1+1]
    if val: sub|=sel
    else:   sub&=~sel

def _stad(m,x0,y0,x1,y1,r,val=True):
    i0,i1=max(0,int((min(x0,x1)-r)/GR)),min(NX-1,int(math.ceil((max(x0,x1)+r)/GR)))
    j0,j1=max(0,int((min(y0,y1)-r)/GR)),min(NY-1,int(math.ceil((max(y0,y1)+r)/GR)))
    if i1<i0 or j1<j0: return
    ii=np.arange(i0,i1+1)*GR; jj=np.arange(j0,j1+1)*GR
    PX=ii[None,:]-x0; PY=jj[:,None]-y0; dx,dy=x1-x0,y1-y0; L2=dx*dx+dy*dy
    if L2<1e-15: d2=PX**2+PY**2
    else:
        t=np.clip((PX*dx+PY*dy)/L2,0,1); d2=(PX-t*dx)**2+(PY-t*dy)**2
    sel=(d2<=r*r); sub=m[j0:j1+1,i0:i1+1]
    if val: sub|=sel
    else:   sub&=~sel

def _rect(m,x0,y0,x1,y1,val=True):
    i0,i1=max(0,int(round(x0/GR))),min(NX-1,int(round(x1/GR)))
    j0,j1=max(0,int(round(y0/GR))),min(NY-1,int(round(y1/GR)))
    if i1<i0 or j1<j0: return
    m[j0:j1+1,i0:i1+1]=val

def paint_pad(m,p,grow=0.0,val=True):
    if p['shape']=='oval':
        w,h=p['w'],p['h']; r=min(w,h)/2
        if h>=w: _stad(m,p['x'],p['y']-(h-w)/2,p['x'],p['y']+(h-w)/2,r+grow,val)
        else:    _stad(m,p['x']-(w-h)/2,p['y'],p['x']+(w-h)/2,p['y'],r+grow,val)
    elif p['shape']=='rect':
        _rect(m,p['x']-p['w']/2-grow,p['y']-p['h']/2-grow,
                p['x']+p['w']/2+grow,p['y']+p['h']/2+grow,val)
    else:
        _disc(m,p['x'],p['y'],max(p['w'],p['h'])/2+grow,val)

def pad_radius(p): return max(p['w'],p['h'])/2

def _shift_and(m, k):
    r = m.copy()
    for _ in range(k):
        s = r.copy()
        s[1:,:] &= r[:-1,:]; s[:-1,:] &= r[1:,:]
        s[:,1:] &= r[:,:-1]; s[:,:-1] &= r[:,1:]
        r = s
    return r

def _shift_or(m, k):
    r = m.copy()
    for _ in range(k):
        s = r.copy()
        s[1:,:] |= r[:-1,:]; s[:-1,:] |= r[1:,:]
        s[:,1:] |= r[:,:-1]; s[:,:-1] |= r[:,1:]
        r = s
    return r

def _open(m, mm):
    """morphological opening: deletes copper slivers narrower than mm"""
    k = max(1, int(round((mm/2)/GR)))
    return _shift_or(_shift_and(m, k), k)

def label4(mask):
    from collections import deque
    NYl,NXl=mask.shape
    lab=np.zeros((NYl,NXl),np.int32); cur=0
    for j0 in range(NYl):
        row=np.nonzero(mask[j0] & (lab[j0]==0))[0]
        for i0 in row:
            if lab[j0,i0]: continue
            cur+=1; dq=deque([(j0,i0)]); lab[j0,i0]=cur
            while dq:
                j,i=dq.popleft()
                for dj,di in ((1,0),(-1,0),(0,1),(0,-1)):
                    nj,ni=j+dj,i+di
                    if 0<=nj<NYl and 0<=ni<NXl and mask[nj,ni] and lab[nj,ni]==0:
                        lab[nj,ni]=cur; dq.append((nj,ni))
    return lab,cur


def _keepout(layer, tracks, vias):
    """area where this layer's pour may NOT go"""
    m=np.zeros((NY,NX),bool)
    _rect(m,EDGE_CU,EDGE_CU,D.BW-EDGE_CU,D.BH-EDGE_CU)
    m = ~m                                    # start: everything outside the board
    for p in D.pads:
        if p['net']=='GND': continue
        paint_pad(m,p,POUR_CLR)
    for (n,l,x0,y0,x1,y1,w) in tracks:
        if n=='GND' or l!=layer: continue
        _stad(m,x0,y0,x1,y1,w/2+POUR_CLR)
    for (n,x,y) in vias:
        if n=='GND': continue
        _disc(m,x,y,D.VIA_D/2+POUR_CLR)
    for (hx,hy,hd) in D.holes:
        _disc(m,hx,hy,hd/2+POUR_CLR)
    if layer==0:
        # Clear only the mark itself, not a box around it: a rectangular
        # exclusion shows up as a panel of bare laminate under the mask. Let
        # the fill hug the logo outline instead - that reads as intentional.
        for it in getattr(D,'accent',[]):
            if it[0]=='line': _stad(m,it[1],it[2],it[3],it[4],it[5]/2+POUR_CLR)
            else:             _disc(m,it[1],it[2],it[3]+POUR_CLR)
    return m


def _thermals(pour, layer):
    gnd=[p for p in D.pads if p['net']=='GND']
    for p in gnd:
        _disc(pour,p['x'],p['y'],pad_radius(p)+TGAP,val=False)
    spokes=np.zeros((NY,NX),bool)
    for p in gnd:
        r=pad_radius(p); reach=r+TGAP+0.30
        _rect(spokes,p['x']-reach,p['y']-SPOKE/2,p['x']+reach,p['y']+SPOKE/2)
        _rect(spokes,p['x']-SPOKE/2,p['y']-reach,p['x']+SPOKE/2,p['y']+reach)
    return spokes


def _raw(layer, tracks, vias):
    """pour before island filtering"""
    block=_keepout(layer, tracks, vias)
    pour = ~block
    legal = pour.copy()
    for p in [q for q in D.pads if q['net']=='GND']:
        _disc(pour,p['x'],p['y'],pad_radius(p)+TGAP,val=False)
    spokes=np.zeros((NY,NX),bool)
    for p in [q for q in D.pads if q['net']=='GND']:
        r=pad_radius(p); reach=r+TGAP+0.30
        _rect(spokes,p['x']-reach,p['y']-SPOKE/2,p['x']+reach,p['y']+SPOKE/2)
        _rect(spokes,p['x']-SPOKE/2,p['y']-reach,p['x']+SPOKE/2,p['y']+reach)
    pour |= (spokes & legal)
    return _open(pour, MIN_W)                 # kill slivers


_CACHE = {}

def build_both(tracks, vias):
    key = (len(tracks), len(vias),
           hash(tuple(sorted(map(repr, tracks)))), hash(tuple(sorted(map(repr, vias)))))
    if key in _CACHE:
        return _CACHE[key]
    r = _build_both(tracks, vias)
    _CACHE[key] = r
    return r


def _build_both(tracks, vias):
    """Ground fill on BOTH layers.

    Returns (top, bottom, stitch_vias). An island that reaches no GND pad is
    floating copper - it is either anchored with a stitching via down to the
    other plane, or removed. A stitch point must have room on BOTH layers,
    otherwise the via would connect to nothing.
    """
    top = _raw(0, tracks, vias)
    bot = _raw(1, tracks, vias)
    gnd_pads = [q for q in D.pads if q['net']=='GND']
    gmask = np.zeros((NY,NX),bool)
    for q in gnd_pads: paint_pad(gmask, q, 0.02)

    k = max(1, int(round(STITCH_R/GR)))
    room_top = _shift_and(top, k)
    room_bot = _shift_and(bot, k)
    both = room_top & room_bot

    stitches=[]
    keep={}
    for layer, m in ((0, top), (1, bot)):
        lab,n = label4(m)
        out = np.zeros_like(m)
        for c in range(1, n+1):
            comp = (lab==c)
            if (comp & gmask).any():
                out |= comp                     # already grounded
                continue
            if comp.sum()*GR*GR < MIN_ISL:
                continue                        # too small to bother, drop it
            cand = comp & both
            ys,xs = np.nonzero(cand)
            if len(xs)==0:
                continue                        # nowhere safe to stitch - drop
            cx, cy = xs.mean(), ys.mean()
            i = int(np.argmin((xs-cx)**2 + (ys-cy)**2))
            pt = (round(float(xs[i])*GR,2), round(float(ys[i])*GR,2))
            stitches.append(('GND', pt[0], pt[1]))
            out |= comp
        keep[layer] = out

    # a stitch via lands in both planes, so it also grounds the island it sits
    # in on the opposite layer - fold that in
    for (_n, sx, sy) in stitches:
        sm = np.zeros((NY,NX),bool); _disc(sm, sx, sy, D.VIA_D/2)
        for layer, m in ((0, top), (1, bot)):
            lab,n = label4(m)
            hit = set(lab[sm & m].tolist()) - {0}
            for c in hit:
                keep[layer] |= (lab==c)
    return keep[0], keep[1], stitches


def build_layer(layer, tracks, vias, stitch=True):
    t,b,s = build_both(tracks, vias)
    return (t if layer==0 else b), s


def build(tracks, vias):
    """bottom pour only - kept for callers that just want B.Cu"""
    return build_both(tracks, vias)[1]


def rects(pour):
    """greedy decomposition of the raster into axis-aligned rectangles (mm)"""
    m=pour.copy(); out=[]
    NYl,NXl=m.shape
    for j in range(NYl):
        i=0
        while i<NXl:
            if not m[j,i]: i+=1; continue
            i2=i
            while i2+1<NXl and m[j,i2+1]: i2+=1
            j2=j
            while j2+1<NYl and m[j2+1,i:i2+1].all(): j2+=1
            m[j:j2+1,i:i2+1]=False
            out.append(((i-0.5)*GR,(j-0.5)*GR,(i2+0.5)*GR,(j2+0.5)*GR))
            i=i2+1
    return out
