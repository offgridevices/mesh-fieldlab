# -*- coding: utf-8 -*-
"""
Packet Logger carrier PCB - design definition.
Coordinates: millimetres, origin at board BOTTOM-LEFT, X right, Y UP.
(The KiCad/Gerber writers flip Y at emit time.)
"""
import math

BW, BH = 86.0, 58.0          # board outline
CLR      = 0.25              # copper clearance
TW_SIG   = 0.25              # signal trace width
TW_PWR   = 0.50              # 3V3 width
TW_BAT   = 0.80              # battery width
VIA_D    = 0.80              # via pad
VIA_DRL  = 0.40

P = 2.54                     # header pitch

pads   = []
outline= []
silk   = []   # ('line',...) / ('text',...) / ('disc',x,y,r,layer)
holes  = []   # NPTH  (x,y,d)
accent = []   # EXPOSED COPPER art: drawn on F.Cu with a matching F.Mask
              # opening, so it reads as bare metal instead of silkscreen.
              # Brand rule: one accent per surface - this is it.

def pad(ref, pin, x, y, net, shape='circle', w=1.6, h=1.6, drill=1.0, dslot=None):
    if str(pin) == '1' and shape == 'circle':
        shape = 'rect'                       # square pad marks pin 1
    pads.append(dict(ref=ref, pin=str(pin), x=x, y=y, net=net, shape=shape,
                     w=w, h=h, drill=drill, dslot=dslot))

def line(x1,y1,x2,y2,w=0.15,layer='silk'):
    silk.append(('line',x1,y1,x2,y2,w,layer))

def rect(x1,y1,x2,y2,w=0.15,layer='silk'):
    line(x1,y1,x2,y1,w,layer); line(x2,y1,x2,y2,w,layer)
    line(x2,y2,x1,y2,w,layer); line(x1,y2,x1,y1,w,layer)

def dashrect(x1,y1,x2,y2,w=0.12,dash=1.2,layer='silk'):
    for (ax,ay,bx,by) in ((x1,y1,x2,y1),(x2,y1,x2,y2),(x2,y2,x1,y2),(x1,y2,x1,y1)):
        L=math.hypot(bx-ax,by-ay); n=max(1,int(L/(dash*2)))
        for i in range(n):
            t0=i*2*dash/L; t1=min(1.0,(i*2+1)*dash/L)
            line(ax+(bx-ax)*t0, ay+(by-ay)*t0, ax+(bx-ax)*t1, ay+(by-ay)*t1, w, layer)

def disc(x,y,r,layer='silk'):
    silk.append(('disc',x,y,r,layer))

def text(x,y,s,size=1.0,just='center',angle=0,layer='silk',thick=None):
    s = s.upper()
    silk.append(('text',x,y,s,size,just,angle,layer,thick if thick else max(0.12,size*0.15)))

def polyline(pts,w=0.15,layer='silk'):
    for k in range(1,len(pts)):
        line(pts[k-1][0],pts[k-1][1],pts[k][0],pts[k][1],w,layer)

def acc_line(x1,y1,x2,y2,w):  accent.append(('line',x1,y1,x2,y2,w,'accent'))
def acc_disc(x,y,r):          accent.append(('disc',x,y,r,'accent'))
def acc_polyline(pts,w):
    for k in range(1,len(pts)):
        acc_line(pts[k-1][0],pts[k-1][1],pts[k][0],pts[k][1],w)

def accent_bbox(m=0.0):
    xs=[]; ys=[]
    for it in accent:
        if it[0]=='line':
            _,x1,y1,x2,y2,w,_l = it
            xs += [min(x1,x2)-w/2, max(x1,x2)+w/2]
            ys += [min(y1,y2)-w/2, max(y1,y2)+w/2]
        else:
            _,x,y,r,_l = it
            xs += [x-r, x+r]; ys += [y-r, y+r]
    if not xs: return None
    return (min(xs)-m, min(ys)-m, max(xs)+m, max(ys)+m)

# ----------------------------------------------------------------- board
outline = [(0,0),(BW,0),(BW,BH),(0,BH)]
for (mx,my) in ((3.5,3.5),(BW-3.5,3.5),(3.5,BH-3.5),(BW-3.5,BH-3.5)):
    holes.append((mx,my,3.2))

# ================================================================= RAK19003
# 8 pins in one line.  Within each group the pitch is 2.54.
# Gap between J6 pin4 (SDA) and J7 pin1 (BOOT) measured from the RAK
# mechanical drawings = 9.41 mm  (NOT a whole number of 0.1" holes!).
# J7 sits at the midpoint of {9.41 (datasheet), 10.16 (3 holes)} on oval
# slots, so either reality solders up.
RAK_PY   = 23.25
RAK_X0   = 6.05
RAK_GAP  = 9.79
J6 = [('VDD','RAW_3V3'),('GND','GND'),('SCL','RAK_SCL'),('SDA','RAK_SDA')]
J7 = [('BOOT','RAK_BOOT'),('GND','GND'),('TX0','RAK_TX0'),('RX0','RAK_RX0')]
for i,(nm,net) in enumerate(J6):
    x = RAK_X0 + i*P
    pad('J1', i+1, x, RAK_PY, net)
    text(x, 17.9, nm, 0.9, angle=90)
J7X0 = RAK_X0 + 3*P + RAK_GAP
for i,(nm,net) in enumerate(J7):
    x = J7X0 + i*P
    pad('J2', i+1, x, RAK_PY, net, shape='oval', w=1.6, h=2.6,
        drill=1.0, dslot=(1.0,2.0))
    text(x, 17.9, nm, 0.9, angle=90)
RAK_BODY = (RAK_X0-3.05, RAK_PY-3.25, J7X0+3*P+2.30, RAK_PY+31.75)
dashrect(*RAK_BODY)
text((RAK_BODY[0]+RAK_BODY[2])/2, RAK_BODY[3]-3.0, 'RAK19003  (35 x 30)', 1.3)
text((RAK_BODY[0]+RAK_BODY[2])/2, RAK_BODY[3]-5.2, 'USB-C / BATT / SOLAR / RESET ON THIS EDGE', 0.8)
text(RAK_X0+1.5*P, RAK_PY+2.3, 'J6', 1.0)
text(J7X0+1.5*P, RAK_PY+2.6, 'J7', 1.0)

# ================================================================= XIAO ESP32-C6
# 2x7, 2.54 pitch, rows 15.24 apart.  USB-C faces EAST.
XI_X0, XI_YB = 66.88, 21.28
XI_YT = XI_YB + 15.24
XBOT = ['D7','D8','D9','D10','3V3','GND','5V']
XTOP = ['D6','D5','D4','D3','D2','D1','D0']
XNET = {'D7':'RAK_TX0','D8':'SD_CLK','D9':'SD_MISO','D10':'SD_MOSI','3V3':'+3V3',
        'GND':'GND','5V':'XIAO_5V','D6':'RAK_RX0','D5':'OLED_SCL','D4':'OLED_SDA',
        'D3':'SD_CS','D2':'XIAO_D2','D1':'XIAO_D1','D0':'BTN'}
for i,nm in enumerate(XBOT):
    x = XI_X0 + i*P
    pad('J3', i+1, x, XI_YB, XNET[nm])
    text(x, 18.3, nm, 0.9, angle=90)
for i,nm in enumerate(XTOP):
    x = XI_X0 + i*P
    pad('J3', 8+i, x, XI_YT, XNET[nm])
    text(x, 39.6, nm, 0.9, angle=90)
XI_BODY = (XI_X0-2.88, XI_YB-1.28, XI_X0+6*P+2.88, XI_YT+1.28)
dashrect(*XI_BODY)
text((XI_BODY[0]+XI_BODY[2])/2, XI_YB+7.6, 'XIAO ESP32-C6', 1.2)
text((XI_BODY[0]+XI_BODY[2])/2, XI_YB+5.6, 'USB-C  ->  EAST', 0.85)

# ================================================================= microSD
# Module is mounted with 3V3 on the LEFT and GND on the RIGHT, body hanging
# SOUTH towards the board edge so the card can be taken in and out.
SD_Y  = 22.0
SD_X0 = 43.65
SDPINS = [('3V3','+3V3'),('CS','SD_CS'),('MOSI','SD_MOSI'),
          ('CLK','SD_CLK'),('MISO','SD_MISO'),('GND','GND')]
for i,(nm,net) in enumerate(SDPINS):
    x = SD_X0 + i*P
    pad('J4', i+1, x, SD_Y, net)
    text(x, 25.0, nm, 0.9, angle=90)
SD_BODY = (38.0, 0.6, 62.0, 22.0)
dashrect(*SD_BODY)
text((SD_BODY[0]+SD_BODY[2])/2, 18.6, 'MICROSD BREAKOUT', 1.1)
text((SD_BODY[0]+SD_BODY[2])/2, 16.8, 'CARD SLOT TOWARDS BOARD EDGE', 0.8)
text((SD_BODY[0]+SD_BODY[2])/2, 15.0, '(24 x 21 reserved - may overhang)', 0.8)

# ================================================================= north headers
NY = 53.0
# --- display: its own four pins, nothing else on this header
OLED = [('GND','GND'),('3V3','+3V3'),('SCL','OLED_SCL'),('SDA','OLED_SDA')]
for i,(nm,net) in enumerate(OLED):
    x = 54.0 + i*P
    pad('J5', i+1, x, NY, net)
    text(x, NY-2.6, nm, 0.85, angle=90)
text(54.0+1.5*P, NY+2.6, 'J5  OLED', 0.95)

# --- external button (in parallel with SW1 on the board)
for i,(nm,net) in enumerate([('BTN','BTN'),('GND','GND')]):
    x = 65.0 + i*P
    pad('J15', i+1, x, NY, net)
    text(x, NY-2.6, nm, 0.85, angle=90)
text(65.0+0.5*P, NY+2.6, 'J15 BTN', 0.95)

# --- spare ESP I/O
ESP = [('5V','XIAO_5V'),('D1','XIAO_D1'),('D2','XIAO_D2'),('GND','GND')]
for i,(nm,net) in enumerate(ESP):
    x = 71.0 + i*P
    pad('J11', i+1, x, NY, net)
    text(x, NY-2.6, nm, 0.8, angle=90)
text(71.0+1.5*P, NY+2.6, 'J11 SPARE', 0.9)

# ================================================================= user button
BTX, BTY = 78.0, 44.5
for i,(dx,dy,net) in enumerate(((-3.25,-2.25,'BTN'),(3.25,-2.25,'GND'),
                                (-3.25, 2.25,None),(3.25, 2.25,None))):
    pad('SW1', i+1, BTX+dx, BTY+dy, net, w=1.8, h=1.8, drill=1.1)
rect(BTX-4.4, BTY-3.7, BTX+4.4, BTY+3.7)
text(BTX-5.9, BTY+2.1, 'SW1 USER', 0.8, just='right')
text(BTX-5.9, BTY+0.3, 'BUTTON', 0.8, just='right')
text(BTX-5.9, BTY-2.25, 'BTN', 0.8, just='right')

# ================================================================= power chain
def hdr(ref, x0, y, n, nets, names, pitch=P, w=1.6, drill=1.0, lbly=-2.4):
    for i in range(n):
        pad(ref, i+1, x0+i*pitch, y, nets[i], w=w, h=w, drill=drill)
        if names[i]: text(x0+i*pitch, y+lbly, names[i], 0.8, angle=90)

hdr('J12', 6.0, 6.0, 2, ['BAT+','GND'], ['B+','B-'])
text(6.0+0.5*P, 6.0+2.4, 'J12 BATT', 0.85)
pad('J13',1,13.0,6.0,'BAT+',w=1.5,h=1.5,drill=0.9)
pad('J13',2,15.0,6.0,'GND', w=1.5,h=1.5,drill=0.9)
rect(11.05,3.6,16.95,8.4)
text(14.0,2.3,'J13 JST-PH', 0.8)

# SS-12D00 / SS12D00G6: 3 pins on 2.54, body 8.0 x 4.0 mm, actuator on top.
# Pin names go BELOW the body outline so nothing overlaps.
hdr('SW2', 20.0, 6.0, 3, ['BAT_SW','BAT+',None], ['OUT','IN','NC'],
    drill=1.1, lbly=-3.4)
rect(22.54-4.0, 6.0-2.0, 22.54+4.0, 6.0+2.0)
text(22.54, 9.0, 'SW2 POWER', 0.85)

hdr('J14', 30.0, 6.0, 2, ['BAT_SW','GND'], ['+','-'])
text(30.0+0.5*P, 6.0+2.4, 'J14 TO RAK', 0.85)

# --- jumper + RAK spare live in the open north-west area, where there is
#     room to label them properly
JPY = 46.0
hdr('JP1', 36.0, JPY, 2, ['RAW_3V3','+3V3'], [None,None])
text(37.27, JPY+2.6, 'JP1 3V3', 0.85)
text(37.27, JPY+4.5, 'FIT SHUNT', 0.8)
text(36.00, JPY-2.7, 'RAK', 0.8, angle=90)
text(38.54, JPY-2.7, 'SYS', 0.8, angle=90)

RSP = [('BOOT','RAK_BOOT'),('SCL','RAK_SCL'),('SDA','RAK_SDA'),('GND','GND')]
for i,(nm,net) in enumerate(RSP):
    x = 43.0 + i*P
    pad('J10', i+1, x, JPY, net)
    text(x, JPY-2.7, nm, 0.8, angle=90)
text(43.0+1.5*P, JPY+2.6, 'J10 RAK SPARE', 0.85)

def cap(ref,x,y,val):
    pad(ref,1,x,y,'+3V3',w=1.4,h=1.4,drill=0.8)
    pad(ref,2,x+P,y,'GND', w=1.4,h=1.4,drill=0.8)
    text(x+P/2,y+2.3,ref+' '+val,0.8)
cap('C1',72.0,12.5,'100u')
cap('C2',39.5,26.5,'10u')
cap('C3',39.5,30.5,'100n')
cap('C4',48.0,53.0,'100n')
text(39.5, 34.2, 'C1-C4 OPTIONAL', 0.8, just='left')

# ================================================================= branding
def offgrid_mark(cx, cy, height=7.0, w=None):
    """OffGrid 'beacon ring': 310 deg arc with the gap at the top, plus a dot.
    Traced directly from public/brand/offgrid-mark.svg (viewBox 0 0 200 200,
    arc r=58 stroke=22 about (100,107.97); dot r=17 at (100,40))."""
    s = height/153.97
    sw = 22*s
    R  = 58*s
    ringy = cy - 7.985*s                     # centre the whole mark on cy
    N=36                                     # segments long enough to survive
    pts=[]                                   # the silkscreen fragment filter
    for k in range(N+1):
        th = math.radians(-65.0 + 310.0*k/N)
        pts.append((cx + R*math.cos(th), ringy - R*math.sin(th)))
    acc_polyline(pts, sw)                    # <- exposed copper, not silkscreen
    acc_disc(cx, ringy + 67.97*s, 17*s)
    return sw

offgrid_mark(68.5, 6.7, 7.0)
text(76.3, 6.7, 'OFFGRID', 1.1, just='left')   # wordmark stays Bone / white silk
# clear space: brand asks for 1x node radius around the mark; the router is
# told to keep all copper out of this box so the metal reads clean.
LOGO_KEEPOUT = accent_bbox(0.9)

# ---- board legend
text(20.0, 56.6, 'PACKET LOGGER CARRIER V1 - 86 X 58', 0.9)

# ---- silkscreen cleanup: nothing may sit on a pad or a hole
import silkclip as _sc
_n0 = len([i for i in silk if i[0] == "line"])
silk[:] = _sc.clip(pads, holes, silk)
_n1 = len([i for i in silk if i[0] == "line"])
