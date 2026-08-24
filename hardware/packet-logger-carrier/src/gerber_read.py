# -*- coding: utf-8 -*-
"""Independent RS-274X reader + rasteriser, used to verify what we wrote."""
import re, math
import numpy as np

class Ras:
    def __init__(self, w, h, res=0.05):
        self.res=res
        self.NX=int(round(w/res))+1; self.NY=int(round(h/res))+1
        self.m=np.zeros((self.NY,self.NX),bool)
    def _bb(self,x0,y0,x1,y1,pad):
        # deliberately conservative: always a superset, so two rasterisations of
        # the same geometry can only differ on the exact boundary
        i0=max(0,int(math.floor((x0-pad)/self.res))-1)
        i1=min(self.NX-1,int(math.ceil((x1+pad)/self.res))+1)
        j0=max(0,int(math.floor((y0-pad)/self.res))-1)
        j1=min(self.NY-1,int(math.ceil((y1+pad)/self.res))+1)
        return i0,i1,j0,j1
    def disc(self,x,y,r,val=True):
        i0,i1,j0,j1=self._bb(x,y,x,y,r)
        if i1<i0 or j1<j0: return
        ii=np.arange(i0,i1+1)*self.res-x; jj=np.arange(j0,j1+1)*self.res-y
        sel=(jj[:,None]**2+ii[None,:]**2<=r*r)
        s=self.m[j0:j1+1,i0:i1+1]
        if val: s|=sel
        else:   s&=~sel
    def rect(self,x,y,w,h,val=True):
        i0=max(0,int(math.ceil((x-w/2)/self.res))); i1=min(self.NX-1,int(math.floor((x+w/2)/self.res)))
        j0=max(0,int(math.ceil((y-h/2)/self.res))); j1=min(self.NY-1,int(math.floor((y+h/2)/self.res)))
        if i1<i0 or j1<j0: return
        self.m[j0:j1+1,i0:i1+1]=val
    def stad(self,x0,y0,x1,y1,r,val=True):
        i0,i1,j0,j1=self._bb(min(x0,x1),min(y0,y1),max(x0,x1),max(y0,y1),r)
        if i1<i0 or j1<j0: return
        ii=np.arange(i0,i1+1)*self.res; jj=np.arange(j0,j1+1)*self.res
        PX=ii[None,:]-x0; PY=jj[:,None]-y0; dx,dy=x1-x0,y1-y0; L2=dx*dx+dy*dy
        if L2<1e-15: d2=PX**2+PY**2
        else:
            t=np.clip((PX*dx+PY*dy)/L2,0,1); d2=(PX-t*dx)**2+(PY-t*dy)**2
        sel=(d2<=r*r); s=self.m[j0:j1+1,i0:i1+1]
        if val: s|=sel
        else:   s&=~sel
    def polygon(self,pts,val=True):
        ys=[p[1] for p in pts]; xs=[p[0] for p in pts]
        i0,i1,j0,j1=self._bb(min(xs),min(ys),max(xs),max(ys),0)
        for j in range(j0,j1+1):
            y=j*self.res; xs_hit=[]
            for k in range(len(pts)):
                (ax,ay)=pts[k]; (bx,by)=pts[(k+1)%len(pts)]
                if (ay<=y<by) or (by<=y<ay):
                    xs_hit.append(ax+(y-ay)*(bx-ax)/(by-ay))
            xs_hit.sort()
            for k in range(0,len(xs_hit)-1,2):
                a,b=xs_hit[k],xs_hit[k+1]
                ia=max(0,int(math.ceil(a/self.res))); ib=min(self.NX-1,int(b/self.res))
                if ib>=ia: self.m[j,ia:ib+1]=val

def parse(path, w, h, res=0.05, ox=0.0, oy=0.0):
    txt=open(path).read()
    ras=Ras(w,h,res)
    aps={}; cur=None; pol=True
    x=y=0.0
    inreg=False; regpts=[]
    scale=1e-6
    arcmode=0            # 0 = linear, 2 = CW, 3 = CCW
    for tok in re.findall(r'%[^%]*%|[^\n*]*\*', txt):
        t=tok.strip()
        if t.startswith('%'):
            body=t.strip('%').strip('*')
            m=re.match(r'ADD(\d+)([CRO]),(.+)',body)
            if m:
                d=int(m.group(1)); shp=m.group(2)
                nums=[float(v) for v in m.group(3).split('X')]
                aps[d]=(shp,nums)
                continue
            m=re.match(r'ADD(\d+)RoundRect,(.+)',body)
            if m:
                d=int(m.group(1))
                v=[float(t) for t in m.group(2).split('X')]
                xs=v[1::2]; ys=v[2::2]
                if xs and ys:
                    aps[d]=('R',[max(xs)-min(xs), max(ys)-min(ys)])
                continue
            m=re.match(r'ADD(\d+)(?:O|Oval),(.+)',body)
            if m:
                d=int(m.group(1))
                aps[d]=('O',[float(t) for t in m.group(2).split('X')])
            elif body=='LPD': pol=True
            elif body=='LPC': pol=False
            continue
        t=t.rstrip('*')
        if not t: continue
        if t=='G36': inreg=True; regpts=[]; continue
        if t=='G37':
            if len(regpts)>=3: ras.polygon(regpts,pol)
            inreg=False; continue
        if t=='G01': arcmode=0; continue
        if t=='G02': arcmode=2; continue
        if t=='G03': arcmode=3; continue
        if t in ('G74','G75','G36x','M02') or t.startswith('G04'): continue
        m=re.match(r'D(\d+)$',t)
        if m:
            d=int(m.group(1))
            if d>=10: cur=d
            continue
        ma=re.match(r'(?:X(-?\d+))?(?:Y(-?\d+))?(?:I(-?\d+))?(?:J(-?\d+))?D0?1$',t)
        if ma and arcmode in (2,3) and (ma.group(3) is not None or ma.group(4) is not None):
            nx = float(ma.group(1))*scale+ox if ma.group(1) is not None else x
            ny = float(ma.group(2))*scale+oy if ma.group(2) is not None else y
            i0 = float(ma.group(3))*scale if ma.group(3) is not None else 0.0
            j0 = float(ma.group(4))*scale if ma.group(4) is not None else 0.0
            cx0, cy0 = x+i0, y+j0
            r0 = math.hypot(x-cx0, y-cy0)
            a0 = math.atan2(y-cy0, x-cx0); a1 = math.atan2(ny-cy0, nx-cx0)
            if arcmode==2:
                while a1 > a0: a1 -= 2*math.pi
                if abs(a1-a0) < 1e-9: a1 = a0-2*math.pi
            else:
                while a1 < a0: a1 += 2*math.pi
                if abs(a1-a0) < 1e-9: a1 = a0+2*math.pi
            n=max(8,int(abs(a1-a0)*r0/0.02))
            prev=(x,y)
            for k in range(1,n+1):
                aa=a0+(a1-a0)*k/n
                pt=(cx0+r0*math.cos(aa), cy0+r0*math.sin(aa))
                if inreg: regpts.append(pt)
                elif cur in aps:
                    shp,nums=aps[cur]
                    ras.stad(prev[0],prev[1],pt[0],pt[1],
                             (nums[0] if shp=='C' else min(nums))/2, pol)
                prev=pt
            x,y=nx,ny
            continue
        mm=re.match(r'(?:X(-?\d+))?(?:Y(-?\d+))?D0?([123])$',t)
        if mm:
            nx = float(mm.group(1))*scale+ox if mm.group(1) is not None else x
            ny = float(mm.group(2))*scale+oy if mm.group(2) is not None else y
            op = mm.group(3)
            if inreg:
                if op=='2': regpts=[(nx,ny)]
                else: regpts.append((nx,ny))
            else:
                if op=='1' and cur in aps:
                    shp,nums=aps[cur]
                    if shp=='C': ras.stad(x,y,nx,ny,nums[0]/2,pol)
                    else: ras.stad(x,y,nx,ny,min(nums)/2,pol)
                elif op=='3' and cur in aps:
                    shp,nums=aps[cur]
                    if shp=='C': ras.disc(nx,ny,nums[0]/2,pol)
                    elif shp=='R': ras.rect(nx,ny,nums[0],nums[1],pol)
                    elif shp=='O':
                        a,b=nums; r=min(a,b)/2
                        if b>=a: ras.stad(nx,ny-(b-a)/2,nx,ny+(b-a)/2,r,pol)
                        else:    ras.stad(nx-(a-b)/2,ny,nx+(a-b)/2,ny,r,pol)
                x,y=nx,ny
            continue
        raise ValueError('unparsed gerber token %r in %s'%(t,path))
    return ras.m
