# -*- coding: utf-8 -*-
import pickle, math
from PIL import Image, ImageDraw, ImageFont
import design as D

S = 16.0          # px per mm
PAD = 8

def load():
    d = pickle.load(open('routed.pkl','rb'))
    return d['tracks'], d['vias']

def F(sz):
    for p in ('/System/Library/Fonts/Supplemental/Arial Narrow.ttf',
              '/System/Library/Fonts/Supplemental/Arial.ttf',
              '/System/Library/Fonts/Helvetica.ttc'):
        try: return ImageFont.truetype(p, max(6,int(sz)))
        except Exception: pass
    return ImageFont.load_default()

def render(out='board.png', show_tracks=True, silkonly=False):
    W = int(D.BW*S)+2*PAD; H = int(D.BH*S)+2*PAD
    im = Image.new('RGB',(W,H),(18,20,24))
    dr = ImageDraw.Draw(im,'RGBA')
    def X(x): return PAD + x*S
    def Y(y): return PAD + (D.BH-y)*S
    # substrate
    dr.rectangle([X(0),Y(D.BH),X(D.BW),Y(0)], fill=(18,58,38))
    import numpy as np, os
    if os.path.exists('pour.npy'):
        pr = np.load('pour.npy')
        ph,pw = pr.shape
        pim = Image.fromarray((pr*255).astype('uint8')).transpose(Image.FLIP_TOP_BOTTOM)
        pim = pim.resize((int(D.BW*S),int(D.BH*S)), Image.NEAREST)
        tint = Image.new('RGBA', pim.size, (52,86,150,120))
        im.paste(tint, (PAD,PAD), pim)
    tracks, vias = load()
    if show_tracks:
        for (n,l,x0,y0,x1,y1,w) in tracks:
            col = (208,92,60,255) if l==0 else (70,120,210,235)
            dr.line([X(x0),Y(y0),X(x1),Y(y1)], fill=col, width=max(1,int(w*S)))
            r=max(1,int(w*S/2))
            for (px,py) in ((x0,y0),(x1,y1)):
                dr.ellipse([X(px)-r,Y(py)-r,X(px)+r,Y(py)+r], fill=col)
    # pads
    for p in D.pads:
        col=(214,178,80,255)
        if p['shape']=='oval':
            w,h=p['w'],p['h']; r=min(w,h)/2
            if h>=w: a=(p['x'],p['y']-(h-w)/2); b=(p['x'],p['y']+(h-w)/2)
            else:    a=(p['x']-(w-h)/2,p['y']); b=(p['x']+(w-h)/2,p['y'])
            dr.line([X(a[0]),Y(a[1]),X(b[0]),Y(b[1])], fill=col, width=int(2*r*S))
            for q in (a,b):
                dr.ellipse([X(q[0])-r*S,Y(q[1])-r*S,X(q[0])+r*S,Y(q[1])+r*S], fill=col)
        elif p['shape']=='rect':
            dr.rectangle([X(p['x']-p['w']/2),Y(p['y']+p['h']/2),
                          X(p['x']+p['w']/2),Y(p['y']-p['h']/2)], fill=col)
        else:
            r=max(p['w'],p['h'])/2
            dr.ellipse([X(p['x'])-r*S,Y(p['y'])-r*S,X(p['x'])+r*S,Y(p['y'])+r*S], fill=col)
        # drill
        if p['dslot']:
            dw,dh=p['dslot']; r=min(dw,dh)/2
            if dh>=dw: a=(p['x'],p['y']-(dh-dw)/2); b=(p['x'],p['y']+(dh-dw)/2)
            else:      a=(p['x']-(dw-dh)/2,p['y']); b=(p['x']+(dw-dh)/2,p['y'])
            dr.line([X(a[0]),Y(a[1]),X(b[0]),Y(b[1])], fill=(12,12,12), width=int(2*r*S))
            for q in (a,b):
                dr.ellipse([X(q[0])-r*S,Y(q[1])-r*S,X(q[0])+r*S,Y(q[1])+r*S], fill=(12,12,12))
        else:
            r=p['drill']/2
            dr.ellipse([X(p['x'])-r*S,Y(p['y'])-r*S,X(p['x'])+r*S,Y(p['y'])+r*S], fill=(12,12,12))
    for (n,x,y) in vias:
        r=D.VIA_D/2
        dr.ellipse([X(x)-r*S,Y(y)-r*S,X(x)+r*S,Y(y)+r*S], fill=(200,170,90,255))
        r=D.VIA_DRL/2
        dr.ellipse([X(x)-r*S,Y(y)-r*S,X(x)+r*S,Y(y)+r*S], fill=(20,20,20))
    for (hx,hy,hd) in D.holes:
        r=hd/2
        dr.ellipse([X(hx)-r*S,Y(hy)-r*S,X(hx)+r*S,Y(hy)+r*S], fill=(10,10,10),
                   outline=(230,230,120), width=2)
    # silk
    for it in D.silk:
        if it[0]=='disc':
            _dx,_dy,_rr = it[1],it[2],it[3]*S
            dr.ellipse([X(_dx)-_rr,Y(_dy)-_rr,X(_dx)+_rr,Y(_dy)+_rr],
                       fill=(238,238,232,225))
        elif it[0]=='line':
            _,x1,y1,x2,y2,w,layer = it
            dr.line([X(x1),Y(y1),X(x2),Y(y2)], fill=(238,238,232,225), width=max(1,int(w*S)))
        else:
            _,x,y,s,size,just,angle,layer,th = it
            f=F(size*S*1.05)
            if angle==0:
                bb=dr.textbbox((0,0),s,font=f)
                w=bb[2]-bb[0]; h=bb[3]-bb[1]
                ax = X(x)-w/2 if just=='center' else X(x)
                dr.text((ax, Y(y)-h/2-bb[1]), s, font=f, fill=(240,240,235,235))
            else:
                tmp=Image.new('RGBA',(int(len(s)*size*S*1.2)+8,int(size*S*2)+8),(0,0,0,0))
                td=ImageDraw.Draw(tmp); td.text((2,2),s,font=f,fill=(240,240,235,235))
                tmp=tmp.rotate(angle,expand=True,resample=Image.BICUBIC)
                bb=tmp.getbbox()
                if bb:
                    tmp=tmp.crop(bb)
                    im.paste(tmp,(int(X(x)-tmp.width/2),int(Y(y)-tmp.height/2)),tmp)
    # outline
    pts=[(X(a),Y(b)) for (a,b) in D.outline]+[(X(D.outline[0][0]),Y(D.outline[0][1]))]
    dr.line(pts, fill=(245,225,110), width=3)
    im.save(out)
    print(out, im.size)

if __name__=='__main__':
    render()
