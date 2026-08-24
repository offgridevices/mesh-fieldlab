# -*- coding: utf-8 -*-
"""Assert the board's net list is exactly the proven perfboard net list."""
import collections, sys
import design as D

byname = collections.defaultdict(set)
for p in D.pads:
    if p['net']: byname[p['net']].add((p['ref'], p['pin']))

# human-readable pad names
LBL = {}
def lab(ref,pin): return LBL.get((ref,pin), '%s.%s'%(ref,pin))
for i,(nm,_) in enumerate(D.J6):  LBL[('J1',str(i+1))] = 'RAK.J6.'+nm
for i,(nm,_) in enumerate(D.J7):  LBL[('J2',str(i+1))] = 'RAK.J7.'+nm
for i,nm in enumerate(D.XBOT):    LBL[('J3',str(i+1))] = 'XIAO.'+nm
for i,nm in enumerate(D.XTOP):    LBL[('J3',str(8+i))] = 'XIAO.'+nm
for i,(nm,_) in enumerate(D.SDPINS): LBL[('J4',str(i+1))] = 'SD.'+nm
for i,(nm,_) in enumerate(D.OLED):   LBL[('J5',str(i+1))] = 'OLED.'+nm
for i,nm in enumerate(['BTN','GND']): LBL[('J15',str(i+1))] = 'EXTBTN.'+nm

EXPECT = {
 'RAK_RX0' : {'RAK.J7.RX0','XIAO.D6'},
 'RAK_TX0' : {'RAK.J7.TX0','XIAO.D7'},
 'SD_CS'   : {'SD.CS','XIAO.D3'},
 'SD_MOSI' : {'SD.MOSI','XIAO.D10'},
 'SD_CLK'  : {'SD.CLK','XIAO.D8'},
 'SD_MISO' : {'SD.MISO','XIAO.D9'},
 'OLED_SCL': {'OLED.SCL','XIAO.D5'},
 'OLED_SDA': {'OLED.SDA','XIAO.D4'},
}
bad=[]
print('%-10s %s' % ('NET','PADS'))
for n in sorted(byname):
    names = sorted(lab(r,p) for (r,p) in byname[n])
    print('%-10s %s' % (n, ', '.join(names)))
for n,exp in EXPECT.items():
    got = {lab(r,p) for (r,p) in byname[n]}
    core = {g for g in got if g.startswith(('RAK.','XIAO.','SD.','OLED.'))}
    if core != exp:
        bad.append('%s: expected %s got %s' % (n, sorted(exp), sorted(core)))

# power / ground membership
p3 = {lab(r,p) for (r,p) in byname['+3V3']}
need3 = {'XIAO.3V3','SD.3V3','OLED.3V3'}
if not need3 <= p3: bad.append('+3V3 missing %s' % sorted(need3-p3))
raw = {lab(r,p) for (r,p) in byname['RAW_3V3']}
if 'RAK.J6.VDD' not in raw: bad.append('RAK VDD not on RAW_3V3')
g = {lab(r,p) for (r,p) in byname['GND']}
needg = {'RAK.J6.GND','RAK.J7.GND','XIAO.GND','SD.GND','OLED.GND'}
if not needg <= g: bad.append('GND missing %s' % sorted(needg-g))
# button
b = {lab(r,p) for (r,p) in byname['BTN']}
if not {'XIAO.D0','EXTBTN.BTN'} <= b: bad.append('BTN wrong: %s'%sorted(b))
if ('SW1','1') not in byname['BTN']: bad.append('SW1 not on BTN')
if ('SW1','2') not in byname['GND']: bad.append('SW1 other side not on GND')
# battery chain
if byname['BAT+']  != {('J12','1'),('J13','1'),('SW2','2')}: bad.append('BAT+ chain wrong: %s'%sorted(byname['BAT+']))
if byname['BAT_SW']!= {('SW2','1'),('J14','1')}: bad.append('BAT_SW chain wrong: %s'%sorted(byname['BAT_SW']))
# no pin used twice / unconnected sanity
print()
if bad:
    for b_ in bad: print('MISMATCH', b_)
    sys.exit(1)
print('NETLIST MATCHES THE PROVEN PERFBOARD WIRING.')
