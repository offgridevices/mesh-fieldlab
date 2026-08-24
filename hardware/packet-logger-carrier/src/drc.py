# -*- coding: utf-8 -*-
"""Independent design-rule / connectivity verification.
Deliberately does NOT reuse the router's obstacle model, so it is a real check."""
import pickle, math, sys
import numpy as np
import design as D

MIN_CLR   = 0.20     # absolute minimum copper-copper (we design to 0.25)
MIN_TRACE = 0.15
MIN_ANN   = 0.15     # annular ring
MIN_H2H   = 0.45     # hole edge to hole edge
EDGE_CU   = 0.30     # copper to board edge
EDGE_DRL  = 0.50
POUR_CLR  = 0.30     # pour to foreign copper

# ------------------------------------------------------------------ geometry
def seg_seg(p,q,r,s):
    (px,py),(qx,qy),(rx,ry),(sx,sy)=p,q,r,s
    d1=(qx-px,qy-py); d2=(sx-rx,sy-ry)
    den=d1[0]*d2[1]-d1[1]*d2[0]
    if abs(den)>1e-12:
        t=((rx-px)*d2[1]-(ry-py)*d2[0])/den
        u=((rx-px)*d1[1]-(ry-py)*d1[0])/den
        if -1e-9<=t<=1+1e-9 and -1e-9<=u<=1+1e-9: return 0.0
    return min(pt_seg(p,r,s),pt_seg(q,r,s),pt_seg(r,p,q),pt_seg(s,p,q))

def pt_seg(p,a,b):
    (px,py),(ax,ay),(bx,by)=p,a,b
    dx,dy=bx-ax,by-ay; L2=dx*dx+dy*dy
    if L2<1e-15: return math.hypot(px-ax,py-ay)
    t=max(0.0,min(1.0,((px-ax)*dx+(py-ay)*dy)/L2))
    return math.hypot(px-(ax+t*dx), py-(ay+t*dy))

class Obj:
    """skeleton = list of segments ; r = inflation ; rect = optional (x0,y0,x1,y1)"""
    __slots__=('net','layers','segs','r','rect','tag')
    def __init__(self,net,layers,segs,r,rect=None,tag=''):
        self.net=net; self.layers=layers; self.segs=segs; self.r=r
        self.rect=rect; self.tag=tag
    def inside(self,p):
        if not self.rect: return False
        x0,y0,x1,y1=self.rect
        return x0<=p[0]<=x1 and y0<=p[1]<=y1

def gap(a,b):
    if a.rect:
        for (p,q) in b.segs:
            if a.inside(p) or a.inside(q): return -(a.r+b.r)
    if b.rect:
        for (p,q) in a.segs:
            if b.inside(p) or b.inside(q): return -(a.r+b.r)
    m=1e9
    for (p,q) in a.segs:
        for (r,s) in b.segs:
            m=min(m,seg_seg(p,q,r,s))
            if m<=0: break
    return m-a.r-b.r

def pad_obj(p):
    L=(0,1)
    if p['shape']=='oval':
        w,h=p['w'],p['h']; r=min(w,h)/2
        if h>=w: segs=[((p['x'],p['y']-(h-w)/2),(p['x'],p['y']+(h-w)/2))]
        else:    segs=[((p['x']-(w-h)/2,p['y']),(p['x']+(w-h)/2,p['y']))]
        return Obj(p['net'],L,segs,r,None,'%s.%s'%(p['ref'],p['pin']))
    if p['shape']=='rect':
        x0,y0=p['x']-p['w']/2,p['y']-p['h']/2; x1,y1=p['x']+p['w']/2,p['y']+p['h']/2
        segs=[((x0,y0),(x1,y0)),((x1,y0),(x1,y1)),((x1,y1),(x0,y1)),((x0,y1),(x0,y0))]
        return Obj(p['net'],L,segs,0.0,(x0,y0,x1,y1),'%s.%s'%(p['ref'],p['pin']))
    r=max(p['w'],p['h'])/2
    return Obj(p['net'],L,[((p['x'],p['y']),(p['x'],p['y']))],r,None,'%s.%s'%(p['ref'],p['pin']))

def build_objs(tracks,vias):
    objs=[]
    for p in D.pads: objs.append(pad_obj(p))
    for i,(n,l,x0,y0,x1,y1,w) in enumerate(tracks):
        objs.append(Obj(n,(l,),[((x0,y0),(x1,y1))],w/2,None,'trk%d'%i))
    for i,(n,x,y) in enumerate(vias):
        objs.append(Obj(n,(0,1),[((x,y),(x,y))],D.VIA_D/2,None,'via%d'%i))
    return objs

# ------------------------------------------------------------------ raster
GR=0.05
def rnx(): return int(round(D.BW/GR))+1
def rny(): return int(round(D.BH/GR))+1

def rdisc(m,x,y,r):
    NX,NY=m.shape[1],m.shape[0]
    i0,i1=max(0,int((x-r)/GR)),min(NX-1,int(math.ceil((x+r)/GR)))
    j0,j1=max(0,int((y-r)/GR)),min(NY-1,int(math.ceil((y+r)/GR)))
    if i1<i0 or j1<j0: return
    ii=np.arange(i0,i1+1)*GR-x; jj=np.arange(j0,j1+1)*GR-y
    m[j0:j1+1,i0:i1+1] |= (jj[:,None]**2+ii[None,:]**2 <= r*r)

def rstad(m,x0,y0,x1,y1,r):
    NX,NY=m.shape[1],m.shape[0]
    i0,i1=max(0,int((min(x0,x1)-r)/GR)),min(NX-1,int(math.ceil((max(x0,x1)+r)/GR)))
    j0,j1=max(0,int((min(y0,y1)-r)/GR)),min(NY-1,int(math.ceil((max(y0,y1)+r)/GR)))
    if i1<i0 or j1<j0: return
    ii=np.arange(i0,i1+1)*GR; jj=np.arange(j0,j1+1)*GR
    PX=ii[None,:]-x0; PY=jj[:,None]-y0; dx,dy=x1-x0,y1-y0; L2=dx*dx+dy*dy
    if L2<1e-15: d2=PX**2+PY**2
    else:
        t=np.clip((PX*dx+PY*dy)/L2,0,1); d2=(PX-t*dx)**2+(PY-t*dy)**2
    m[j0:j1+1,i0:i1+1] |= (d2<=r*r)

def rrect(m,x0,y0,x1,y1,grow=0.0):
    NX,NY=m.shape[1],m.shape[0]
    i0,i1=max(0,int((x0-grow)/GR)),min(NX-1,int(math.ceil((x1+grow)/GR)))
    j0,j1=max(0,int((y0-grow)/GR)),min(NY-1,int(math.ceil((y1+grow)/GR)))
    if i1>=i0 and j1>=j0: m[j0:j1+1,i0:i1+1]=True

def paint_pad(m,p,grow=0.0):
    if p['shape']=='oval':
        w,h=p['w'],p['h']; r=min(w,h)/2
        if h>=w: rstad(m,p['x'],p['y']-(h-w)/2,p['x'],p['y']+(h-w)/2,r+grow)
        else:    rstad(m,p['x']-(w-h)/2,p['y'],p['x']+(w-h)/2,p['y'],r+grow)
    elif p['shape']=='rect':
        rrect(m,p['x']-p['w']/2,p['y']-p['h']/2,p['x']+p['w']/2,p['y']+p['h']/2,grow)
    else:
        rdisc(m,p['x'],p['y'],max(p['w'],p['h'])/2+grow)

def label(mask):
    """4-connected labelling, returns (labels, count)"""
    NY,NX=mask.shape
    lab=np.zeros((NY,NX),dtype=np.int32); cur=0
    idx=np.argwhere(mask)
    seen=np.zeros_like(mask)
    from collections import deque
    for (j0,i0) in idx:
        if seen[j0,i0]: continue
        cur+=1; dq=deque([(j0,i0)]); seen[j0,i0]=True
        while dq:
            j,i=dq.popleft(); lab[j,i]=cur
            for dj,di in ((1,0),(-1,0),(0,1),(0,-1)):
                nj,ni=j+dj,i+di
                if 0<=nj<NY and 0<=ni<NX and mask[nj,ni] and not seen[nj,ni]:
                    seen[nj,ni]=True; dq.append((nj,ni))
    return lab,cur

# ------------------------------------------------------------------ checks
def run():
    d=pickle.load(open('routed.pkl','rb'))
    tracks,vias=d['tracks'],d['vias']
    errs=[]; warns=[]

    # ---- 1. pairwise clearance
    objs=build_objs(tracks,vias)
    n=len(objs)
    for i in range(n):
        a=objs[i]
        for j in range(i+1,n):
            b=objs[j]
            if a.net==b.net and a.net is not None: continue
            if a.net is None and b.net is None: continue
            if not (set(a.layers)&set(b.layers)): continue
            g=gap(a,b)
            if g < MIN_CLR-1e-6:
                errs.append('CLEARANCE %.3f mm  %s(%s) <-> %s(%s)'%(g,a.tag,a.net,b.tag,b.net))

    # ---- 2. track width / board edge
    for (nt,l,x0,y0,x1,y1,w) in tracks:
        if w<MIN_TRACE-1e-9: errs.append('TRACE WIDTH %.3f on %s'%(w,nt))
        for (x,y) in ((x0,y0),(x1,y1)):
            if not (EDGE_CU+w/2 <= x <= D.BW-EDGE_CU-w/2 and
                    EDGE_CU+w/2 <= y <= D.BH-EDGE_CU-w/2):
                errs.append('TRACK OUTSIDE EDGE KEEPOUT %s @ %.2f,%.2f'%(nt,x,y))

    # ---- 3. annular ring + drill + edge
    allholes=[]
    for p in D.pads:
        if p['dslot']: dw,dh=p['dslot']
        else: dw=dh=p['drill']
        ann=min(p['w']-dw,p['h']-dh)/2
        if ann<MIN_ANN-1e-9:
            errs.append('ANNULAR %.3f on %s.%s'%(ann,p['ref'],p['pin']))
        allholes.append((p['x'],p['y'],dw,dh,'%s.%s'%(p['ref'],p['pin'])))
    for (n_,x,y) in vias:
        ann=(D.VIA_D-D.VIA_DRL)/2
        if ann<MIN_ANN-1e-9: errs.append('VIA ANNULAR %.3f'%ann)
        allholes.append((x,y,D.VIA_DRL,D.VIA_DRL,'via'))
    for (hx,hy,hd) in D.holes: allholes.append((hx,hy,hd,hd,'MH'))
    for i in range(len(allholes)):
        xi,yi,wi,hi,ti=allholes[i]
        if not (EDGE_DRL+wi/2<=xi<=D.BW-EDGE_DRL-wi/2 and
                EDGE_DRL+hi/2<=yi<=D.BH-EDGE_DRL-hi/2):
            errs.append('HOLE TOO CLOSE TO EDGE %s @ %.2f,%.2f'%(ti,xi,yi))
        for j in range(i+1,len(allholes)):
            xj,yj,wj,hj,tj=allholes[j]
            dx=abs(xi-xj)-(wi+wj)/2; dy=abs(yi-yj)-(hi+hj)/2
            if dx<0 and dy<0: dd=max(dx,dy)
            elif dx<0: dd=dy
            elif dy<0: dd=dx
            else: dd=math.hypot(dx,dy)
            if dd<MIN_H2H-1e-6:
                errs.append('HOLE-HOLE %.3f  %s <-> %s'%(dd,ti,tj))

    # ---- 4. connectivity per net (raster flood fill, 2 layers)
    NX,NY=rnx(),rny()
    nets=sorted({p['net'] for p in D.pads if p['net']})
    for net in nets:
        if net=='GND': continue
        cu=[np.zeros((NY,NX),bool),np.zeros((NY,NX),bool)]
        via_cells=[]
        for p in D.pads:
            if p['net']!=net: continue
            for l in (0,1): paint_pad(cu[l],p)
            via_cells.append((p['x'],p['y']))
        for (nt,l,x0,y0,x1,y1,w) in tracks:
            if nt!=net: continue
            rstad(cu[l],x0,y0,x1,y1,w/2)
        for (nt,x,y) in vias:
            if nt!=net: continue
            for l in (0,1): rdisc(cu[l],x,y,D.VIA_D/2)
            via_cells.append((x,y))
        # flood across both layers, transitions at via_cells
        start=None
        pl=[p for p in D.pads if p['net']==net]
        s=pl[0]; start=(0,int(round(s['x']/GR)),int(round(s['y']/GR)))
        from collections import deque
        seen=[np.zeros((NY,NX),bool),np.zeros((NY,NX),bool)]
        dq=deque([start]); seen[0][start[2],start[1]]=True
        vc=set((int(round(x/GR)),int(round(y/GR))) for (x,y) in via_cells)
        vcell=np.zeros((NY,NX),bool)
        for (n_,x,y) in vias: rdisc(vcell,x,y,D.VIA_DRL/2)
        for p in D.pads:
            if p['net']==net: paint_pad(vcell,p,-0.2)
        while dq:
            l,i,j=dq.popleft()
            for dj,di in ((1,0),(-1,0),(0,1),(0,-1)):
                ni,nj=i+di,j+dj
                if 0<=ni<NX and 0<=nj<NY and cu[l][nj,ni] and not seen[l][nj,ni]:
                    seen[l][nj,ni]=True; dq.append((l,ni,nj))
            if vcell[j,i]:
                ol=1-l
                if cu[ol][j,i] and not seen[ol][j,i]:
                    seen[ol][j,i]=True; dq.append((ol,i,j))
        for p in pl:
            i=int(round(p['x']/GR)); j=int(round(p['y']/GR))
            if not (seen[0][j,i] or seen[1][j,i]):
                errs.append('NOT CONNECTED  net %s  pad %s.%s'%(net,p['ref'],p['pin']))

    # ---- 5. GND pour
    pour=np.zeros((NY,NX),bool)
    rrect(pour,EDGE_CU,EDGE_CU,D.BW-EDGE_CU,D.BH-EDGE_CU)
    block=np.zeros((NY,NX),bool)
    for p in D.pads:
        if p['net']=='GND': continue
        paint_pad(block,p,POUR_CLR)
    for (nt,l,x0,y0,x1,y1,w) in tracks:
        if nt=='GND' or l!=1: continue
        rstad(block,x0,y0,x1,y1,w/2+POUR_CLR)
    for (nt,x,y) in vias:
        if nt=='GND': continue
        rdisc(block,x,y,D.VIA_D/2+POUR_CLR)
    for (hx,hy,hd) in D.holes: rdisc(block,hx,hy,hd/2+POUR_CLR)
    pour &= ~block
    lab,ncomp=label(pour)
    sizes=np.bincount(lab.ravel()); sizes[0]=0
    main=int(np.argmax(sizes))
    islands=[k for k in range(1,ncomp+1) if k!=main and sizes[k]>0]
    isl_big=[k for k in islands if sizes[k]*GR*GR>1.0]
    gpads=[p for p in D.pads if p['net']=='GND']
    for p in gpads:
        i=int(round(p['x']/GR)); j=int(round(p['y']/GR))
        r=int(round((max(p['w'],p['h'])/2+POUR_CLR+0.15)/GR))
        ok=False
        for jj in range(max(0,j-r),min(NY,j+r+1)):
            for ii in range(max(0,i-r),min(NX,i+r+1)):
                if lab[jj,ii]==main: ok=True; break
            if ok: break
        if not ok: errs.append('GND PAD NOT REACHED BY POUR: %s.%s'%(p['ref'],p['pin']))
    if isl_big:
        warns.append('pour has %d isolated island(s) >1mm2 (areas mm2: %s) - will be removed'
                     %(len(isl_big), [round(sizes[k]*GR*GR,1) for k in isl_big]))

    np.save('pour.npy', (lab==main))
    print('--- DRC ---')
    print('objects=%d tracks=%d vias=%d holes=%d'%(len(objs),len(tracks),len(vias),len(allholes)))
    for w in warns: print('WARN ', w)
    if errs:
        for e in errs[:60]: print('ERROR', e)
        print('TOTAL ERRORS:', len(errs))
    else:
        print('PASS: no clearance, connectivity, drill or edge violations.')
    return errs

if __name__=='__main__':
    sys.exit(1 if run() else 0)
