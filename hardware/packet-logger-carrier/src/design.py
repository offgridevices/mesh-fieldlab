# -*- coding: utf-8 -*-
"""
Packet Logger carrier PCB - design definition.
Coordinates: millimetres, origin at board BOTTOM-LEFT, X right, Y UP.
(The KiCad/Gerber writers flip Y at emit time.)
"""

BW, BH = 86.0, 58.0          # board outline
CLR      = 0.25              # copper clearance
TW_SIG   = 0.25              # signal trace width
TW_PWR   = 0.50              # 3V3 width
TW_BAT   = 0.80              # battery width
VIA_D    = 0.80              # via pad
VIA_DRL  = 0.40

P = 2.54                     # header pitch

pads   = []   # dicts: ref,pin,x,y,shape,w,h,drill,dslot,net,name
outline= []
silk   = []   # ('line',x1,y1,x2,y2,w) / ('text',x,y,s,size,just,angle) / ('circle',..)
holes  = []   # NPTH  (x,y,d)
fab    = []

def pad(ref, pin, x, y, net, shape='circle', w=1.6, h=1.6, drill=1.0, dslot=None):
    if str(pin) == '1' and shape == 'circle':
        shape = 'rect'
    pads.append(dict(ref=ref, pin=str(pin), x=x, y=y, net=net, shape=shape,
                     w=w, h=h, drill=drill, dslot=dslot))

def line(x1,y1,x2,y2,w=0.15,layer='silk'):
    silk.append(('line',x1,y1,x2,y2,w,layer))

def rect(x1,y1,x2,y2,w=0.15,layer='silk'):
    line(x1,y1,x2,y1,w,layer); line(x2,y1,x2,y2,w,layer)
    line(x2,y2,x1,y2,w,layer); line(x1,y2,x1,y1,w,layer)

def dashrect(x1,y1,x2,y2,w=0.12,dash=1.2,layer='silk'):
    import math
    for (ax,ay,bx,by) in ((x1,y1,x2,y1),(x2,y1,x2,y2),(x2,y2,x1,y2),(x1,y2,x1,y1)):
        L=math.hypot(bx-ax,by-ay); n=max(1,int(L/(dash*2)))
        for i in range(n):
            t0=i*2*dash/L; t1=min(1.0,(i*2+1)*dash/L)
            line(ax+(bx-ax)*t0, ay+(by-ay)*t0, ax+(bx-ax)*t1, ay+(by-ay)*t1, w, layer)

def text(x,y,s,size=1.0,just='center',angle=0,layer='silk',thick=None):
    s = s.upper()
    silk.append(('text',x,y,s,size,just,angle,layer,thick if thick else max(0.12,size*0.15)))

# ----------------------------------------------------------------- board
outline = [(0,0),(BW,0),(BW,BH),(0,BH)]
for (mx,my) in ((3.5,3.5),(BW-3.5,3.5),(3.5,BH-3.5),(BW-3.5,BH-3.5)):
    holes.append((mx,my,3.2))

# ================================================================= RAK19003
# 8 pins in one line.  Within each group the pitch is 2.54.
# Gap between J6 pin4 (SDA) and J7 pin1 (BOOT) measured from the RAK
# mechanical drawings = 9.41 mm  (NOT a whole number of 0.1" holes!).
# We place the J7 group at the midpoint of {9.41 (datasheet), 10.16 (3 holes)}
# and give it oval slots so either reality solders up.
RAK_PY   = 23.25
RAK_X0   = 6.05
RAK_GAP  = 9.79              # nominal, slots absorb 9.24 .. 10.34
J6 = [('VDD','RAW_3V3'),('GND','GND'),('SCL','RAK_SCL'),('SDA','RAK_SDA')]
J7 = [('BOOT','RAK_BOOT'),('GND','GND'),('TX0','RAK_TX0'),('RX0','RAK_RX0')]
RAK_PINS = {}
for i,(nm,net) in enumerate(J6):
    x = RAK_X0 + i*P
    pad('J1', i+1, x, RAK_PY, net); RAK_PINS[nm+'6']=(x,RAK_PY)
    text(x, RAK_PY-2.35, nm, 0.85, angle=90)
J7X0 = RAK_X0 + 3*P + RAK_GAP
for i,(nm,net) in enumerate(J7):
    x = J7X0 + i*P
    pad('J2', i+1, x, RAK_PY, net, shape='oval', w=1.6, h=2.6,
        drill=1.0, dslot=(1.0,2.0)); RAK_PINS[nm+'7']=(x,RAK_PY)
    text(x, RAK_PY-2.9, nm, 0.85, angle=90)
RAK_BODY = (RAK_X0-3.05, RAK_PY-3.25, J7X0+3*P+2.30, RAK_PY+31.75)
dashrect(*RAK_BODY)
text((RAK_BODY[0]+RAK_BODY[2])/2, RAK_BODY[3]-3.0, 'RAK19003  (35 x 30)', 1.3)
text((RAK_BODY[0]+RAK_BODY[2])/2, RAK_BODY[3]-5.2, 'USB-C / BATT / SOLAR / RESET ON THIS EDGE', 0.8)
text(RAK_X0+1.5*P, RAK_PY+2.2, 'J6', 1.0)
text(J7X0+1.5*P, RAK_PY+2.2, 'J7', 1.0)

# ================================================================= XIAO ESP32-C6
# 2x7, 2.54 pitch, rows 15.24 apart. Mounted with USB-C facing EAST.
XI_X0, XI_YB = 66.88, 21.28
XI_YT = XI_YB + 15.24
XBOT = ['D7','D8','D9','D10','3V3','GND','5V']
XTOP = ['D6','D5','D4','D3','D2','D1','D0']
XNET = {'D7':'RAK_TX0','D8':'SD_CLK','D9':'SD_MISO','D10':'SD_MOSI','3V3':'+3V3',
        'GND':'GND','5V':'XIAO_5V','D6':'RAK_RX0','D5':'OLED_SCL','D4':'OLED_SDA',
        'D3':'SD_CS','D2':'XIAO_D2','D1':'XIAO_D1','D0':'BTN'}
XI = {}
for i,nm in enumerate(XBOT):
    x = XI_X0 + i*P
    pad('J3', i+1, x, XI_YB, XNET[nm]); XI[nm]=(x,XI_YB)
    text(x, XI_YB-2.35, nm, 0.85, angle=90)
for i,nm in enumerate(XTOP):
    x = XI_X0 + i*P
    pad('J3', 8+i, x, XI_YT, XNET[nm]); XI[nm]=(x,XI_YT)
    text(x, XI_YT+2.35, nm, 0.85, angle=90)
XI_BODY = (XI_X0-2.88, XI_YB-1.28, XI_X0+6*P+2.88, XI_YT+1.28)
dashrect(*XI_BODY)
text((XI_BODY[0]+XI_BODY[2])/2, XI_YB+7.0, 'XIAO ESP32-C6', 1.2)
text((XI_BODY[0]+XI_BODY[2])/2, XI_YB+5.0, 'USB-C  ->  EAST', 0.85)

# ================================================================= microSD
SD_Y  = 22.0
SD_X0 = 42.65
SDPINS = [('GND','GND'),('MISO','SD_MISO'),('CLK','SD_CLK'),
          ('MOSI','SD_MOSI'),('CS','SD_CS'),('3V3','+3V3')]
SD = {}
for i,(nm,net) in enumerate(SDPINS):
    x = SD_X0 + i*P
    pad('J4', i+1, x, SD_Y, net); SD[nm]=(x,SD_Y)
    text(x, SD_Y-2.35, nm, 0.85, angle=90)
SD_BODY = (39.0, 20.0, 63.0, 42.0)
dashrect(*SD_BODY)
text((SD_BODY[0]+SD_BODY[2])/2, SD_BODY[3]-2.6, 'microSD BREAKOUT', 1.2)
text((SD_BODY[0]+SD_BODY[2])/2, SD_BODY[3]-4.6, 'module body sits in this box', 0.8)
text((SD_BODY[0]+SD_BODY[2])/2, SD_BODY[3]-6.2, '(24 x 22 reserved - may overhang)', 0.7)

# ================================================================= LID header
LID_Y = 53.0
LIDP = [('GND','GND'),('3V3','+3V3'),('SCL','OLED_SCL'),('SDA','OLED_SDA'),('BTN','BTN')]
for i,(nm,net) in enumerate(LIDP):
    x = 58.0 + i*P
    pad('J5', i+1, x, LID_Y, net)
    text(x, LID_Y-2.35, nm, 0.85, angle=90)
text(58.0+2*P, LID_Y+2.6, 'J5  OLED + BUTTON', 0.95)

# ================================================================= spare breakouts
# split in two so neither one drags long traces across the board
RSP = [('BOOT','RAK_BOOT'),('rSCL','RAK_SCL'),('rSDA','RAK_SDA'),('GND','GND')]
for i,(nm,net) in enumerate(RSP):
    x = 16.0 + i*P
    pad('J10', i+1, x, 13.0, net)
    text(x, 13.0-2.35, nm, 0.8, angle=90)
text(16.0+1.5*P, 13.0+2.4, 'J10  RAK SPARE', 0.9)

ESP = [('5V','XIAO_5V'),('D1','XIAO_D1'),('D2','XIAO_D2'),('GND','GND')]
for i,(nm,net) in enumerate(ESP):
    x = 72.0 + i*P
    pad('J11', i+1, x, LID_Y, net)
    text(x, LID_Y-2.35, nm, 0.8, angle=90)
text(72.0+1.5*P, LID_Y+2.6, 'J11 SPARE', 0.9)

# ================================================================= button
BTX, BTY = 78.0, 44.5
for i,(dx,dy,net) in enumerate(((-3.25,-2.25,'BTN'),(3.25,-2.25,'GND'),
                                (-3.25, 2.25,None),(3.25, 2.25,None))):
    pad('SW1', i+1, BTX+dx, BTY+dy, net, w=1.8, h=1.8, drill=1.1)
rect(BTX-3.0, BTY-3.0, BTX+3.0, BTY+3.0)
text(BTX, BTY+4.2, 'SW1 USER BUTTON', 0.85)
text(BTX-3.25, BTY-4.3, 'BTN', 0.7)

# ================================================================= power chain
def hdr(ref, x0, y, n, nets, names, pitch=P, w=1.6, drill=1.0, lbly=-2.35):
    for i in range(n):
        pad(ref, i+1, x0+i*pitch, y, nets[i], w=w, h=w, drill=drill)
        if names[i]: text(x0+i*pitch, y+lbly, names[i], 0.8, angle=90)

hdr('J12', 6.0, 6.0, 2, ['BAT+','GND'], ['B+','B-'])
text(6.0+0.5*P, 6.0+2.4, 'J12 BATT', 0.85)
pad('J13',1,13.0,6.0,'BAT+',w=1.5,h=1.5,drill=0.9)
pad('J13',2,15.0,6.0,'GND', w=1.5,h=1.5,drill=0.9)
rect(11.05,3.6,16.95,8.4)
text(14.0,2.7,'J13 JST-PH', 0.75)
hdr('SW2', 20.0, 6.0, 3, ['BAT_SW','BAT+',None], ['OUT','IN','NC'])
text(20.0+1.0*P, 6.0+2.4, 'SW2 POWER', 0.85)
hdr('J14', 30.0, 6.0, 2, ['BAT_SW','GND'], ['+','-'])
text(30.0+0.5*P, 6.0+2.4, 'J14 TO RAK', 0.85)
hdr('JP1', 8.0, 13.0, 2, ['RAW_3V3','+3V3'], [None,None])
text(8.0+0.5*P, 13.0+2.4, 'JP1 3V3', 0.85)
text(8.0-1.6, 13.0, 'RAK', 0.7, just='right')
text(10.54+1.6, 13.0, 'SYS', 0.7, just='left')

def cap(ref,x,y,val):
    pad(ref,1,x,y,'+3V3',w=1.4,h=1.4,drill=0.8)
    pad(ref,2,x+P,y,'GND', w=1.4,h=1.4,drill=0.8)
    text(x+P/2,y+2.2,ref+' '+val,0.75)
cap('C1',72.0,10.0,'100u')
cap('C2',58.0,10.0,'10u')
cap('C3',58.0,14.5,'100n')
cap('C4',49.0,53.0,'100n')
text(43.0, 2.9, 'C1..C4 OPTIONAL - BOARD WORKS WITHOUT THEM', 0.7, just='left')

# ---- board legend
text(BW/2, 1.6, 'PACKET LOGGER CARRIER  v1  -  86 x 58 mm  -  2 layer', 1.0)
