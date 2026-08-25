# -*- coding: utf-8 -*-
"""Grid maze router (A*), 2 layers, mm grid.  Clearance is baked into the
obstacle rasterisation, so a routed net physically cannot violate spacing."""
import heapq, math
import numpy as np
import design as D

G      = 0.10                      # grid pitch mm
NX     = int(round(D.BW/G))+1
NY     = int(round(D.BH/G))+1
NL     = 2                         # 0 = F.Cu (top), 1 = B.Cu (bottom)
EDGE_KEEP = 0.6                    # copper must stay this far inside the outline

def gx(x): return int(round(x/G))
def gy(y): return int(round(y/G))
def mx(i): return i*G
def my(j): return j*G

def disc(mask, x, y, r):
    if r <= 0: return
    i0,i1 = max(0,gx(x-r)), min(NX-1,gx(x+r))
    j0,j1 = max(0,gy(y-r)), min(NY-1,gy(y+r))
    if i1<i0 or j1<j0: return
    ii = np.arange(i0,i1+1)*G - x
    jj = np.arange(j0,j1+1)*G - y
    d2 = jj[:,None]**2 + ii[None,:]**2
    mask[j0:j1+1, i0:i1+1] |= (d2 <= r*r)

def box(mask, x0,y0,x1,y1, grow):
    i0,i1 = max(0,gx(x0-grow)), min(NX-1,gx(x1+grow))
    j0,j1 = max(0,gy(y0-grow)), min(NY-1,gy(y1+grow))
    if i1<i0 or j1<j0: return
    mask[j0:j1+1, i0:i1+1] = True

def stadium(mask, x0,y0,x1,y1, r):
    """thick line with round caps"""
    if r<=0: return
    lo_x,hi_x = min(x0,x1)-r, max(x0,x1)+r
    lo_y,hi_y = min(y0,y1)-r, max(y0,y1)+r
    i0,i1 = max(0,gx(lo_x)), min(NX-1,gx(hi_x))
    j0,j1 = max(0,gy(lo_y)), min(NY-1,gy(hi_y))
    if i1<i0 or j1<j0: return
    ii = np.arange(i0,i1+1)*G
    jj = np.arange(j0,j1+1)*G
    PX = ii[None,:]-x0; PY = jj[:,None]-y0
    dx,dy = x1-x0, y1-y0
    L2 = dx*dx+dy*dy
    if L2 < 1e-12:
        d2 = PX**2+PY**2
    else:
        t = np.clip((PX*dx+PY*dy)/L2, 0.0, 1.0)
        d2 = (PX-t*dx)**2 + (PY-t*dy)**2
    mask[j0:j1+1, i0:i1+1] |= (d2 <= r*r)

def pad_extent(p):
    """returns (kind, params) describing pad copper"""
    if p['shape']=='rect':
        return ('rect', (p['x']-p['w']/2, p['y']-p['h']/2,
                         p['x']+p['w']/2, p['y']+p['h']/2))
    if p['shape']=='oval':
        # stadium of width w, height h -> segment along the long axis
        w,h = p['w'],p['h']
        if h>=w:
            return ('seg', (p['x'], p['y']-(h-w)/2, p['x'], p['y']+(h-w)/2, w/2))
        return ('seg', (p['x']-(w-h)/2, p['y'], p['x']+(w-h)/2, p['y'], h/2))
    return ('disc', (p['x'], p['y'], max(p['w'],p['h'])/2))

class Router:
    def __init__(self):
        self.tracks = []           # (net, layer, x0,y0,x1,y1, width)
        self.vias   = []           # (net, x, y)

    # ---------------------------------------------------------- obstacles
    def build(self, net, tw, half=None):
        """blocked[l] = True where the CENTRE of a `tw`-wide trace of `net`
        may not be placed."""
        blk = np.zeros((NL,NY,NX), dtype=bool)
        half = (tw/2.0) if half is None else half
        # board edge
        m = EDGE_KEEP + half
        for l in range(NL):
            blk[l][:, :max(0,gx(m))] = True
            blk[l][:, min(NX,gx(D.BW-m))+1:] = True
            blk[l][:max(0,gy(m)), :] = True
            blk[l][min(NY,gy(D.BH-m))+1:, :] = True
        # brand accent art is exposed copper on F.Cu - nothing may route through it
        kz = getattr(D, 'LOGO_KEEPOUT', None)
        if kz:
            box(blk[0], kz[0], kz[1], kz[2], kz[3], half)
        # NPTH mounting holes (both layers)
        for (hx,hy,hd) in D.holes:
            for l in range(NL):
                disc(blk[l], hx,hy, hd/2 + 0.3 + D.CLR + half)
        # pads
        for p in D.pads:
            same = (p['net']==net)
            if same:
                continue                      # own-net pads are targets
            k,par = pad_extent(p)
            grow = D.CLR + half
            # Keep BOTTOM-layer copper well clear of GND pads.  The ground pour
            # lives on B.Cu and has to be able to reach every GND pad through
            # its thermal spokes; a trace squeezing past on both sides fences
            # the pad off.  1.0 mm leaves room for a 0.65 mm spoke.
            growb = max(grow, 1.00 + half) if p['net']=='GND' else grow
            gl = (grow, growb)
            if k=='disc':
                x,y,r = par
                for l in range(NL): disc(blk[l], x,y, r+gl[l])
            elif k=='rect':
                x0,y0,x1,y1 = par
                for l in range(NL): box(blk[l], x0,y0,x1,y1, gl[l])
            else:
                x0,y0,x1,y1,r = par
                for l in range(NL): stadium(blk[l], x0,y0,x1,y1, r+gl[l])
        # existing tracks
        for (n,l,x0,y0,x1,y1,w) in self.tracks:
            if n==net: continue
            stadium(blk[l], x0,y0,x1,y1, w/2 + D.CLR + half)
        for (n,x,y) in self.vias:
            if n==net: continue
            for l in range(NL): disc(blk[l], x,y, D.VIA_D/2 + D.CLR + half)
        return blk

    def net_pads(self, net):
        return [p for p in D.pads if p['net']==net]

    # ---------------------------------------------------------- A*
    def route_net(self, net, tw, prefer_top=True, allow_via=True):
        tps = self.net_pads(net)
        if len(tps) < 2: return True, 0
        blk  = self.build(net, tw)
        blkv = self.build(net, tw, half=D.VIA_D/2.0)
        # cells that satisfy the rule but sit in the tight band near foreign
        # copper: legal, just discouraged, so traces drift to the middle of gaps
        tight = self.build(net, tw, half=tw/2.0 + 0.22) & ~blk
        # seed set = pad 0 ; then connect each remaining pad to the tree
        def pad_cells(p):
            """Arrival is the pad CENTRE only.  Letting the router stop anywhere
            on the pad made traces clip in at the edge, which leaves an acute
            trace/pad corner (an etch trap) and hangs the joint off the thinnest
            part of the annular ring."""
            cx, cy = p['x'], p['y']
            if p['dslot']:
                dw, dh = p['dslot']
                # an oval slot may legitimately be entered along its long axis
                if dh >= dw:
                    return _span(cx, cy, 0.0, (dh - dw) / 2 - 0.15)
                return _span(cx, cy, (dw - dh) / 2 - 0.15, 0.0)
            return _span(cx, cy, 0.0, 0.0)

        def _span(cx, cy, ax, ay, rad=0.055):
            cells = set()
            for j in range(gy(cy - ay - rad), gy(cy + ay + rad) + 1):
                for i in range(gx(cx - ax - rad), gx(cx + ax + rad) + 1):
                    if 0 <= i < NX and 0 <= j < NY:
                        for l in range(NL):
                            cells.add((l, i, j))
            return cells

        def _pad_cells_full(p):
            cells=set()
            k,par = pad_extent(p)
            if k=='rect':
                x0,y0,x1,y1 = par
                for j in range(max(0,gy(y0+0.15)),min(NY-1,gy(y1-0.15))+1):
                    for i in range(max(0,gx(x0+0.15)),min(NX-1,gx(x1-0.15))+1):
                        for l in range(NL): cells.add((l,i,j))
                return cells
            if k=='disc':
                x,y,r = par
                for j in range(max(0,gy(y-r)),min(NY-1,gy(y+r))+1):
                    for i in range(max(0,gx(x-r)),min(NX-1,gx(x+r))+1):
                        if (mx(i)-x)**2+(my(j)-y)**2 <= (max(0.25,r-0.15))**2:
                            for l in range(NL): cells.add((l,i,j))
            else:
                x0,y0,x1,y1,r = par
                n=12
                for t in range(n+1):
                    x=x0+(x1-x0)*t/n; y=y0+(y1-y0)*t/n
                    for j in range(max(0,gy(y-r)),min(NY-1,gy(y+r))+1):
                        for i in range(max(0,gx(x-r)),min(NX-1,gx(x+r))+1):
                            if (mx(i)-x)**2+(my(j)-y)**2 <= (max(0.25,r-0.15))**2:
                                for l in range(NL): cells.add((l,i,j))
            return cells

        tree = pad_cells(tps[0])
        nvia = 0
        for p in tps[1:]:
            goal = pad_cells(p)
            if tree & goal:
                tree |= goal; continue
            path = self._astar(blk, tree, goal, prefer_top, allow_via, blkv, tight)
            if path is None:
                return False, nvia
            # emit
            segs, vs = self._emit(path, net, tw)
            self.tracks += segs
            self.vias   += vs
            nvia += len(vs)
            for (l,i,j) in path: tree.add((l,i,j))
            tree |= goal
            # re-block against ourselves for next terminal? same net -> no
            blk  = self.build(net, tw)
            blkv = self.build(net, tw, half=D.VIA_D/2.0)
            tight = self.build(net, tw, half=tw/2.0 + 0.22) & ~blk
        return True, nvia

    def _astar(self, blk, starts, goals, prefer_top, allow_via, blkv=None, tight=None):
        gset = goals
        # goal centroid for heuristic
        gs = list(gset)
        gi = sum(c[1] for c in gs)/len(gs); gj = sum(c[2] for c in gs)/len(gs)
        def h(l,i,j): return (abs(i-gi)+abs(j-gj))*1.0
        INF = float('inf')
        dist = {}
        prev = {}
        pq = []
        for (l,i,j) in starts:
            if 0<=i<NX and 0<=j<NY and not blk[l,j,i]:
                dist[(l,i,j)] = 0.0
                heapq.heappush(pq,(h(l,i,j),0.0,(l,i,j),None))
        found=None
        VIA_COST   = 55.0
        TURN_COST  = 1.2
        BOT_COST   = 0.35      # discourage eating the ground plane
        TIGHT_COST = 2.5       # prefer the middle of a gap to its edge
        while pq:
            f,g,(l,i,j),pdir = heapq.heappop(pq)
            if g > dist.get((l,i,j),INF)+1e-9: continue
            if (l,i,j) in gset:
                found=(l,i,j); break
            for (di,dj) in ((1,0),(-1,0),(0,1),(0,-1)):
                ni,nj = i+di, j+dj
                if not (0<=ni<NX and 0<=nj<NY): continue
                if blk[l,nj,ni]: continue
                c = 1.0 + (BOT_COST if l==1 else 0.0)
                if tight is not None and tight[l,nj,ni]: c += TIGHT_COST
                if pdir is not None and pdir!=(di,dj): c += TURN_COST
                ng = g + c
                key=(l,ni,nj)
                if ng < dist.get(key,INF)-1e-9:
                    dist[key]=ng; prev[key]=((l,i,j),(di,dj))
                    heapq.heappush(pq,(ng+h(l,ni,nj), ng, key,(di,dj)))
            if allow_via:
                nl = 1-l
                if (not blkv[nl,j,i]) and (not blkv[l,j,i]):
                    ng = g + VIA_COST
                    key=(nl,i,j)
                    if ng < dist.get(key,INF)-1e-9:
                        dist[key]=ng; prev[key]=((l,i,j),None)
                        heapq.heappush(pq,(ng+h(nl,i,j), ng, key,None))
        if found is None: return None
        path=[found]
        while path[-1] in prev:
            path.append(prev[path[-1]][0])
        path.reverse()
        return path

    def _emit(self, path, net, tw):
        segs=[]; vias=[]
        run=[path[0]]
        for k in range(1,len(path)):
            a,b = path[k-1], path[k]
            if a[0]!=b[0]:
                if len(run)>1: segs += self._poly(run, net, tw)
                vias.append((net, mx(a[1]), my(a[2])))
                run=[b]
            else:
                run.append(b)
        if len(run)>1: segs += self._poly(run, net, tw)
        return segs, vias

    def _poly(self, run, net, tw):
        pts=[run[0]]
        for k in range(1,len(run)-1):
            a,b,c = run[k-1],run[k],run[k+1]
            if (b[1]-a[1],b[2]-a[2]) != (c[1]-b[1],c[2]-b[2]):
                pts.append(b)
        pts.append(run[-1])
        out=[]
        for k in range(1,len(pts)):
            l=pts[k][0]
            out.append((net,l,mx(pts[k-1][1]),my(pts[k-1][2]),
                              mx(pts[k][1]),  my(pts[k][2]), tw))
        return out
