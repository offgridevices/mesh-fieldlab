# -*- coding: utf-8 -*-
import csv, collections, os
import design as D

FRIENDLY = {
 'J1':('RAK19003 header J6','1x4 2.54 female header'),
 'J2':('RAK19003 header J7','1x4 2.54 female header (OVAL SLOTS)'),
 'J3':('XIAO ESP32-C6','2x7 2.54 female header, rows 15.24 apart'),
 'J4':('microSD breakout','1x6 2.54 female header'),
 'J5':('OLED display','1x4 2.54 male header'),
 'J15':('External button (parallel with SW1)','1x2 2.54 male header'),
 'J10':('RAK spare I/O','1x4 2.54 male header'),
 'J11':('ESP spare I/O','1x4 2.54 male header'),
 'J12':('Battery in (bare wires)','1x2 2.54'),
 'J13':('Battery in (JST-PH 2.0)','S2B-PH-K-S or solder wires'),
 'J14':('Switched battery out to RAK','1x2 2.54 + JST-PH pigtail'),
 'SW1':('User button','6 mm through-hole tact switch'),
 'SW2':('Power switch','SS-12D00 / SS12D00G6 slide switch, 3 pins on 2.54'),
 'JP1':('3V3 link','1x2 header + shunt (or solder blob)'),
 'C1':('Bulk decoupling','100 uF electrolytic, 2.54 lead pitch, OPTIONAL'),
 'C2':('SD decoupling','10 uF, 2.54 lead pitch, OPTIONAL'),
 'C3':('SD decoupling','100 nF, 2.54 lead pitch, OPTIONAL'),
 'C4':('OLED decoupling','100 nF, 2.54 lead pitch, OPTIONAL'),
}
LBL={}
for i,(nm,_) in enumerate(D.J6):  LBL[('J1',str(i+1))]='RAK J6 '+nm
for i,(nm,_) in enumerate(D.J7):  LBL[('J2',str(i+1))]='RAK J7 '+nm
for i,nm in enumerate(D.XBOT):    LBL[('J3',str(i+1))]='XIAO '+nm
for i,nm in enumerate(D.XTOP):    LBL[('J3',str(8+i))]='XIAO '+nm
for i,(nm,_) in enumerate(D.SDPINS): LBL[('J4',str(i+1))]='SD '+nm
for i,(nm,_) in enumerate(D.OLED):   LBL[('J5',str(i+1))]='OLED '+nm
for i,nm in enumerate(['BTN','GND']): LBL[('J15',str(i+1))]='EXT BTN '+nm
for i,(nm,_) in enumerate(D.RSP): LBL[('J10',str(i+1))]='RAK '+nm
for i,nm in enumerate(['5V','D1','D2','GND']): LBL[('J11',str(i+1))]='XIAO '+nm

def go(outdir):
    os.makedirs(outdir,exist_ok=True)
    with open(os.path.join(outdir,'netlist.csv'),'w',newline='') as f:
        w=csv.writer(f); w.writerow(['net','ref','pin','signal','x_mm','y_mm'])
        for p in sorted(D.pads,key=lambda q:(q['net'] or '~', q['ref'], int(q['pin']))):
            w.writerow([p['net'] or '(none)', p['ref'], p['pin'],
                        LBL.get((p['ref'],p['pin']),''), round(p['x'],2), round(p['y'],2)])
    with open(os.path.join(outdir,'bom.csv'),'w',newline='') as f:
        w=csv.writer(f); w.writerow(['ref','pins','what','part'])
        g=collections.OrderedDict()
        for p in D.pads: g.setdefault(p['ref'],0); g[p['ref']]+=1
        for ref,n in g.items():
            a,b=FRIENDLY.get(ref,(ref,''))
            w.writerow([ref,n,a,b])
        w.writerow(['H1-H4',4,'Mounting holes','M3 clearance, 3.2 mm, non-plated'])
    print('wrote netlist.csv and bom.csv;', len(D.pads),'pads')

if __name__=='__main__': go('out')
