# -*- coding: utf-8 -*-
"""RS-274X Gerber + Excellon writer.  Gerber is Y-up, same frame as design.py."""
import os, pickle, math, datetime
import design as D
import strokefont as SF
import pour as PR

MASK_EXP = 0.05          # soldermask expansion per side
BASE = 'packet-logger-carrier'

def C(v): return '%d' % int(round(v*1e6))          # 4.6 format, mm

class Gbr:
    def __init__(self, func, polarity='Positive'):
        self.l=[]; self.ap={}; self.n=10; self.cur=None
        self.l.append('%FSLAX46Y46*%')
        self.l.append('%MOMM*%')
        self.l.append('%TF.GenerationSoftware,cairn,packet-logger-carrier,1.0*%')
        self.l.append('%TF.CreationDate,'+datetime.datetime(2026,8,24).isoformat()+'*%')
        self.l.append('%TF.FileFunction,'+func+'*%')
        self.l.append('%TF.FilePolarity,'+polarity+'*%')
        self.l.append('%TF.SameCoordinates,Original*%')
        self.l.append('G04 Packet Logger Carrier v1*')
        self.l.append('G01*')
        self.l.append('%LPD*%')
        self._defs=[]
    def ad(self, spec):
        if spec in self.ap: return self.ap[spec]
        d=self.n; self.n+=1; self.ap[spec]=d
        if spec[0]=='C':   s='C,%.6f'%spec[1]
        elif spec[0]=='R': s='R,%.6fX%.6f'%(spec[1],spec[2])
        elif spec[0]=='O': s='O,%.6fX%.6f'%(spec[1],spec[2])
        else: raise ValueError(spec)
        self._defs.append('%%ADD%d%s*%%'%(d,s))
        return d
    def use(self,d):
        if self.cur!=d: self.l.append('D%d*'%d); self.cur=d
    def flash(self,spec,x,y):
        self.use(self.ad(spec)); self.l.append('X%sY%sD03*'%(C(x),C(y)))
    def draw(self,spec,x0,y0,x1,y1):
        self.use(self.ad(spec))
        self.l.append('X%sY%sD02*'%(C(x0),C(y0)))
        self.l.append('X%sY%sD01*'%(C(x1),C(y1)))
    def poly(self,spec,pts):
        for k in range(1,len(pts)):
            self.draw(spec,pts[k-1][0],pts[k-1][1],pts[k][0],pts[k][1])
    def region(self,pts):
        self.l.append('G36*')
        self.l.append('X%sY%sD02*'%(C(pts[0][0]),C(pts[0][1])))
        for (x,y) in pts[1:]:
            self.l.append('X%sY%sD01*'%(C(x),C(y)))
        self.l.append('X%sY%sD01*'%(C(pts[0][0]),C(pts[0][1])))
        self.l.append('G37*')
        self.cur=None
    def save(self,path):
        head=self.l[:11]; body=self.l[11:]
        out=head+self._defs+body+['M02*']
        open(path,'w').write('\n'.join(out)+'\n')
        return len(out)

def pad_spec(p, grow=0.0):
    if p['shape']=='rect':  return ('R', p['w']+2*grow, p['h']+2*grow)
    if p['shape']=='oval':  return ('O', p['w']+2*grow, p['h']+2*grow)
    return ('C', max(p['w'],p['h'])+2*grow)

def emit(outdir):
    os.makedirs(outdir, exist_ok=True)
    d=pickle.load(open('routed.pkl','rb')); tracks,vias=d['tracks'],d['vias']
    ptop, pbot, _st = PR.build_both(tracks, vias)
    prects = {0: PR.rects(ptop), 1: PR.rects(pbot)}
    files=[]

    # ---------------- copper
    for (layer, func, fn) in ((0,'Copper,L1,Top','F_Cu'),(1,'Copper,L2,Bot','B_Cu')):
        g=Gbr(func)
        for (x0,y0,x1,y1) in prects[layer]:
            g.region([(x0,y0),(x1,y0),(x1,y1),(x0,y1)])
        for (n,l,x0,y0,x1,y1,w) in tracks:
            if l!=layer: continue
            g.draw(('C',w),x0,y0,x1,y1)
        for p in D.pads:
            g.flash(pad_spec(p), p['x'], p['y'])
        for (n,x,y) in vias:
            g.flash(('C',D.VIA_D), x, y)
        if layer==0:
            for it in getattr(D,'accent',[]):
                if it[0]=='line': g.draw(('C',it[5]), it[1],it[2],it[3],it[4])
                else:             g.flash(('C',round(2*it[3],4)), it[1],it[2])
        f=os.path.join(outdir,'%s-%s.gbr'%(BASE,fn)); g.save(f); files.append(f)

    # ---------------- soldermask (pads open, vias tented)
    for (func,fn) in (('Soldermask,Top','F_Mask'),('Soldermask,Bot','B_Mask')):
        g=Gbr(func,'Negative')
        for p in D.pads:
            g.flash(pad_spec(p,MASK_EXP), p['x'], p['y'])
        for (hx,hy,hd) in D.holes:
            g.flash(('C', round(hd+2*MASK_EXP,4)), hx, hy)
        if fn=='F_Mask':
            for it in getattr(D,'accent',[]):
                if it[0]=='line': g.draw(('C',it[5]), it[1],it[2],it[3],it[4])
                else:             g.flash(('C',round(2*it[3],4)), it[1],it[2])
        f=os.path.join(outdir,'%s-%s.gbr'%(BASE,fn)); g.save(f); files.append(f)

    # ---------------- silkscreen
    g=Gbr('Legend,Top','Positive')
    for it in D.silk:
        if it[0]=='disc':
            _,dx,dy,dr,_l = it
            g.flash(('C', round(2*dr,4)), dx, dy)
        elif it[0]=='poly':
            g.region(list(it[1]))
        elif it[0]=='line':
            _,x1,y1,x2,y2,w,lay=it
            g.draw(('C',w),x1,y1,x2,y2)
        else:
            _,x,y,s,size,just,angle,lay,th=it
            for pl in SF.strokes(s,x,y,size,just,angle):
                g.poly(('C',round(th,3)),pl)
    f=os.path.join(outdir,'%s-F_Silkscreen.gbr'%BASE); g.save(f); files.append(f)

    # ---------------- profile
    g=Gbr('Profile,NP','Positive')
    pts=D.outline+[D.outline[0]]
    g.poly(('C',0.1),pts)
    f=os.path.join(outdir,'%s-Edge_Cuts.gbr'%BASE); g.save(f); files.append(f)

    # ---------------- drill
    def drl(path, items, plated):
        tools={}
        for it in items:
            tools.setdefault(round(it[2],3), []).append(it)
        L=['M48',
           ';DRILL file {packet-logger-carrier} date 2026-08-24',
           ';FORMAT={-:-/ absolute / metric / decimal}',
           'FMAT,2','METRIC,TZ',
           '%s'%(';TYPE=PLATED' if plated else ';TYPE=NON_PLATED')]
        for i,dia in enumerate(sorted(tools)):
            L.append('T%dC%.3f'%(i+1,dia))
        L.append('%'); L.append('G90'); L.append('G05')
        for i,dia in enumerate(sorted(tools)):
            L.append('T%d'%(i+1))
            for it in tools[dia]:
                if len(it)>3 and it[3] is not None:
                    (sx,sy),(ex,ey)=it[3]
                    L.append('X%.3fY%.3fG85X%.3fY%.3f'%(sx,sy,ex,ey))
                else:
                    L.append('X%.3fY%.3f'%(it[0],it[1]))
        L.append('T0'); L.append('M30')
        open(path,'w').write('\n'.join(L)+'\n')

    pth=[]
    for p in D.pads:
        if p['dslot']:
            dw,dh=p['dslot']
            if dh>=dw: seg=((p['x'],p['y']-(dh-dw)/2),(p['x'],p['y']+(dh-dw)/2)); dia=dw
            else:      seg=((p['x']-(dw-dh)/2,p['y']),(p['x']+(dw-dh)/2,p['y'])); dia=dh
            pth.append((p['x'],p['y'],dia,seg))
        else:
            pth.append((p['x'],p['y'],p['drill'],None))
    for (n,x,y) in vias: pth.append((x,y,D.VIA_DRL,None))
    f=os.path.join(outdir,'%s-PTH.drl'%BASE); drl(f,pth,True); files.append(f)
    npth=[(hx,hy,hd,None) for (hx,hy,hd) in D.holes]
    f=os.path.join(outdir,'%s-NPTH.drl'%BASE); drl(f,npth,False); files.append(f)

    for f in files:
        print('  %-52s %8d B'%(os.path.basename(f), os.path.getsize(f)))
    return files

if __name__=='__main__':
    emit('out/gerbers')
