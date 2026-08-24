# -*- coding: utf-8 -*-
"""Round-trip check: rasterise emitted Gerbers and compare to the model."""
import pickle, numpy as np, os
import design as D, pour as PR, gerber_read as GR
import strokefont as SF

RES=0.05
def blank(): return GR.Ras(D.BW,D.BH,RES)

def model_copper(layer, tracks, vias, prects):
    r=blank()
    if layer==1:
        for (x0,y0,x1,y1) in prects: r.polygon([(x0,y0),(x1,y0),(x1,y1),(x0,y1)])
    for (n,l,x0,y0,x1,y1,w) in tracks:
        if l==layer: r.stad(x0,y0,x1,y1,w/2)
    for p in D.pads:
        if p['shape']=='rect': r.rect(p['x'],p['y'],p['w'],p['h'])
        elif p['shape']=='oval':
            a,b=p['w'],p['h']; rr=min(a,b)/2
            if b>=a: r.stad(p['x'],p['y']-(b-a)/2,p['x'],p['y']+(b-a)/2,rr)
            else:    r.stad(p['x']-(a-b)/2,p['y'],p['x']+(a-b)/2,p['y'],rr)
        else: r.disc(p['x'],p['y'],max(p['w'],p['h'])/2)
    for (n,x,y) in vias: r.disc(x,y,D.VIA_D/2)
    return r.m

def main():
    d=pickle.load(open('routed.pkl','rb')); tracks,vias=d['tracks'],d['vias']
    prects=PR.rects(PR.build(tracks,vias))
    ok=True
    for (layer,fn) in ((0,'F_Cu'),(1,'B_Cu')):
        got=GR.parse('out/gerbers/packet-logger-carrier-%s.gbr'%fn, D.BW,D.BH,RES)
        exp=model_copper(layer,tracks,vias,prects)
        def dil(m):
            r=m.copy()
            r[1:,:]|=m[:-1,:]; r[:-1,:]|=m[1:,:]
            r[:,1:]|=m[:,:-1]; r[:,:-1]|=m[:,1:]
            return r
        # tolerate a one-cell boundary band (geometry lands exactly on grid lines)
        bad = (exp & ~dil(got)) | (got & ~dil(exp))
        a=bad.sum()*RES*RES
        print('%-6s gerber=%.1f mm2  model=%.1f mm2  real mismatch=%.4f mm2 (%d cells)'
              %(fn, got.sum()*RES*RES, exp.sum()*RES*RES, a, bad.sum()))
        if bad.sum()>0: ok=False
    for fn in ('F_Mask','B_Mask','Edge_Cuts','F_Silkscreen'):
        m=GR.parse('out/gerbers/packet-logger-carrier-%s.gbr'%fn, D.BW,D.BH,RES)
        print('%-14s parsed, %.1f mm2 of features'%(fn, m.sum()*RES*RES))
    print('ROUND TRIP:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1

if __name__=='__main__':
    raise SystemExit(main())
