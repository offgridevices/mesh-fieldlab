# -*- coding: utf-8 -*-
"""B.Cu ground pour with thermal reliefs, as a raster + rectangle decomposition."""
import math
import numpy as np
import design as D

GR       = 0.05
POUR_CLR = 0.35      # generated clearance (spec minimum is 0.20)
EDGE_CU  = 0.35
TGAP     = 0.35      # thermal gap
SPOKE    = 0.65      # thermal spoke width
MIN_ISL  = 0.8       # mm^2 - drop islands smaller than this

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

def build(tracks, vias):
    pour=np.zeros((NY,NX),bool)
    _rect(pour,EDGE_CU,EDGE_CU,D.BW-EDGE_CU,D.BH-EDGE_CU)
    # keep out foreign copper
    for p in D.pads:
        if p['net']=='GND': continue
        paint_pad(pour,p,POUR_CLR,val=False)
    for (n,l,x0,y0,x1,y1,w) in tracks:
        if n=='GND' or l!=1: continue
        _stad(pour,x0,y0,x1,y1,w/2+POUR_CLR,val=False)
    for (n,x,y) in vias:
        if n=='GND': continue
        _disc(pour,x,y,D.VIA_D/2+POUR_CLR,val=False)
    for (hx,hy,hd) in D.holes:
        _disc(pour,hx,hy,hd/2+POUR_CLR,val=False)
    # thermal reliefs on GND pads
    gnd=[p for p in D.pads if p['net']=='GND']
    for p in gnd:
        r=pad_radius(p)
        _disc(pour,p['x'],p['y'],r+TGAP,val=False)
    spokes=np.zeros((NY,NX),bool)
    for p in gnd:
        r=pad_radius(p); reach=r+TGAP+0.30
        _rect(spokes,p['x']-reach,p['y']-SPOKE/2,p['x']+reach,p['y']+SPOKE/2)
        _rect(spokes,p['x']-SPOKE/2,p['y']-reach,p['x']+SPOKE/2,p['y']+reach)
    # spokes must still respect foreign clearance / holes / edge
    legal=np.zeros((NY,NX),bool)
    _rect(legal,EDGE_CU,EDGE_CU,D.BW-EDGE_CU,D.BH-EDGE_CU)
    for p in D.pads:
        if p['net']=='GND': continue
        paint_pad(legal,p,POUR_CLR,val=False)
    for (n,l,x0,y0,x1,y1,w) in tracks:
        if n=='GND' or l!=1: continue
        _stad(legal,x0,y0,x1,y1,w/2+POUR_CLR,val=False)
    for (n,x,y) in vias:
        if n=='GND': continue
        _disc(legal,x,y,D.VIA_D/2+POUR_CLR,val=False)
    for (hx,hy,hd) in D.holes:
        _disc(legal,hx,hy,hd/2+POUR_CLR,val=False)
    pour |= (spokes & legal)
    # drop islands
    lab,n=label4(pour)
    if n:
        sizes=np.bincount(lab.ravel()); sizes[0]=0
        main=int(np.argmax(sizes))
        for k in range(1,n+1):
            if k!=main and sizes[k]*GR*GR < 1e9:   # keep only main
                if k!=main: pour[lab==k]=False
        pour = (lab==main)
    return pour

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
