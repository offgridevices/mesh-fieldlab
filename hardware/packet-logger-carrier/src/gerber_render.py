# -*- coding: utf-8 -*-
"""Render the EMITTED gerbers (not the model) to a realistic board image."""
import numpy as np, re, math
from PIL import Image
import design as D, gerber_read as GR

RES=0.02
B='out/gerbers/packet-logger-carrier-'

def drills():
    m=GR.Ras(D.BW,D.BH,RES)
    for path in (B+'PTH.drl', B+'NPTH.drl'):
        tool={}; cur=None
        for ln in open(path):
            ln=ln.strip()
            t=re.match(r'T(\d+)C([\d.]+)$',ln)
            if t: tool[int(t.group(1))]=float(t.group(2)); continue
            t=re.match(r'T(\d+)$',ln)
            if t: cur=tool.get(int(t.group(1))); continue
            t=re.match(r'X([-\d.]+)Y([-\d.]+)G85X([-\d.]+)Y([-\d.]+)$',ln)
            if t and cur:
                m.stad(float(t.group(1)),float(t.group(2)),
                       float(t.group(3)),float(t.group(4)),cur/2); continue
            t=re.match(r'X([-\d.]+)Y([-\d.]+)$',ln)
            if t and cur: m.disc(float(t.group(1)),float(t.group(2)),cur/2)
    return m.m

def render(out='fab.png', bottom=False):
    cu   = GR.parse(B+('B_Cu' if bottom else 'F_Cu')+'.gbr', D.BW,D.BH,RES)
    mask = GR.parse(B+('B_Mask' if bottom else 'F_Mask')+'.gbr', D.BW,D.BH,RES)
    silk = GR.parse(B+'F_Silkscreen.gbr', D.BW,D.BH,RES) if not bottom else np.zeros_like(cu)
    dr   = drills()
    H,W = cu.shape
    img=np.zeros((H,W,3),np.uint8)
    # ---- OffGrid palette, as the board will actually be ordered ----
    #   matte black soldermask  ~ Pitch  #1B1813
    #   white silkscreen        ~ Bone   #F1ECE0
    #   ENIG exposed copper     = the single Ember accent, in metal
    img[:,:] = (27,24,19)                      # Pitch: mask over bare FR4
    img[cu]  = (37,33,26)                      # mask sitting on copper
    ex = mask & cu
    img[ex]  = (205,170,100)                   # ENIG gold - pads + the mark
    img[mask & ~cu] = (120,104,74)             # opening with no copper behind
    img[silk]= (241,236,224)                   # Bone
    img[dr]  = (8,7,6)                         # Coal
    im=Image.fromarray(img[::-1])              # gerber Y-up -> image Y-down
    im=im.resize((int(W*0.42),int(H*0.42)), Image.LANCZOS)
    bg=Image.new('RGB',(im.width+24,im.height+24),(16,13,9))   # Coal surround
    bg.paste(im,(12,12)); bg.save(out)
    print(out, bg.size)

if __name__=='__main__':
    render('fab_top.png', False)
    render('fab_bottom.png', True)
