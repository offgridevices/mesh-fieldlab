# -*- coding: utf-8 -*-
"""Detect silkscreen text collisions (text-text and text-pad)."""
import design as D, strokefont as SF

def tbox(it):
    _,x,y,s,size,just,angle,layer,th = it
    w = SF.width(s,size); h = size*1.25
    if   just=='center': x0=-w/2
    elif just=='right':  x0=-w
    else:                x0=0.0
    bx=(x0, -h/2, x0+w, h/2)
    if angle % 180 == 90:
        return (x-bx[3], y+bx[0], x-bx[1], y+bx[2])
    return (x+bx[0], y+bx[1], x+bx[2], y+bx[3])

def pbox(p, m=0.05):
    return (p['x']-p['w']/2-m, p['y']-p['h']/2-m, p['x']+p['w']/2+m, p['y']+p['h']/2+m)

def ov(a,b):
    ix = min(a[2],b[2])-max(a[0],b[0])
    iy = min(a[3],b[3])-max(a[1],b[1])
    return (ix,iy) if (ix>0 and iy>0) else None

def run(verbose=True):
    texts=[it for it in D.silk if it[0]=='text']
    hits=[]
    for i in range(len(texts)):
        for j in range(i+1,len(texts)):
            o=ov(tbox(texts[i]),tbox(texts[j]))
            if o and o[0]>0.25 and o[1]>0.25:
                hits.append(('TEXT/TEXT','%r'%texts[i][3],'%r'%texts[j][3],round(o[0],2),round(o[1],2)))
    for t in texts:
        for p in D.pads:
            o=ov(tbox(t), pbox(p))
            if o and o[0]>0.15 and o[1]>0.15:
                hits.append(('TEXT/PAD','%r'%t[3],'%s.%s'%(p['ref'],p['pin']),round(o[0],2),round(o[1],2)))
    # text outside board
    for t in texts:
        b=tbox(t)
        if b[0]<0.5 or b[1]<0.5 or b[2]>D.BW-0.5 or b[3]>D.BH-0.5:
            hits.append(('OFF-BOARD','%r'%t[3],'',round(b[0],1),round(b[2],1)))
    if verbose:
        for h in hits: print('  %-10s %-42s %-16s ov=%.2f x %.2f'%h)
        print('silk collisions:', len(hits))
    return hits

if __name__=='__main__':
    import sys; sys.exit(1 if run() else 0)
